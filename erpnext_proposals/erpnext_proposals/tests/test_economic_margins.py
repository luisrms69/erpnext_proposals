# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Pruebas de rentabilidad con MÁRGENES DIFERENTES por producto y contratos mixtos.

Verifica (motor `economic_calendar._evaluate_doc`, sin BD): margen individual por línea, margen PONDERADO
de la propuesta (calculado desde ingresos/costos TOTALES, NUNCA promediando %), costos por periodo, TCV y
contratos de distinta duración. Documento in-memory CONGELADO (docstatus=1 + proposal_template) para que
el motor lea los valores materializados por línea (sin resolución viva ni dependencias del site)."""

import unittest

import frappe
from frappe.utils import flt

from erpnext_proposals.erpnext_proposals.utils.economic_calendar import _evaluate_doc

# Escenario: 3 productos con márgenes distintos y duraciones mixtas.
#   anual   : margen 15%, recurring Year/1, compromiso 24m -> 2 facturaciones (Mes 0 y 12)
#   mensual : margen 25%, recurring Month/1, compromiso 12m -> 12 facturaciones
#   unico   : margen 40%, one_time (NRC), Mes 0
_LINES = [
	# (code, cost_unit, qty, behavior, interval, commitment, margin_pct)
	("ANUAL", 100.0, 10, "recurring", "Year", 24, 15.0),
	("MENSUAL", 50.0, 15, "recurring", "Month", 12, 25.0),
	("UNICO", 200.0, 5, "one_time", "", 0, 40.0),
]


def _roundup2(v):
	import math

	return math.ceil(round(flt(v) * 100.0, 6)) / 100.0


def _sale_unit(cost, margin_pct):
	return _roundup2(cost / (1.0 - margin_pct / 100.0))


def _build_doc():
	d = frappe.get_doc(
		{
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"currency": "MXN",  # base == doc -> to_base=1 (sin FX; aísla la prueba de margen)
			"conversion_rate": 1.0,
			"transaction_date": frappe.utils.today(),
			"proposal_template": "T-MARGENES",
			"proposal_contract_term_months": 0,
		}
	)
	for code, cost, qty, beh, interval, commit, mpct in _LINES:
		rate = _sale_unit(cost, mpct)
		d.append(
			"items",
			{
				"item_code": code,
				"qty": qty,
				"rate": rate,
				"amount": rate * qty,
				"net_amount": rate * qty,
				"proposal_economic_behavior": beh,
				"proposal_billing_interval": interval,
				"proposal_billing_interval_count": 1 if beh == "recurring" else 0,
				"proposal_commitment_months": commit,
				"proposal_frozen_cost_source": "buying_item_price",
				"proposal_frozen_cost_rate": cost,  # costo en base (MXN)
			},
		)
	d.docstatus = 1
	return d


class TestEconomicMargins(unittest.TestCase):
	def setUp(self):
		self.m = _evaluate_doc(_build_doc(), term=0)
		self.lines = {ln["item_code"]: ln for g in self.m["groups"].values() for ln in g["lines"]}

	def test_individual_margin_per_product(self):
		for code, _cost, _qty, _beh, _interval, _commit, mpct in _LINES:
			ln = self.lines[code]
			self.assertAlmostEqual(ln["margin_pct"], mpct, places=1, msg=f"margen individual {code}")

	def test_weighted_margin_from_totals_not_average_of_pct(self):
		t = self.m["totals"]
		weighted = t["margin"] / t["revenue"] * 100.0
		# Ponderado = margen_total / ingreso_total (NO el promedio simple de 15/25/40 = 26.667%).
		simple_avg = (15.0 + 25.0 + 40.0) / 3.0
		self.assertNotAlmostEqual(weighted, simple_avg, places=1)
		# Recalculado a mano desde los TCV de cada línea.
		exp = (
			sum(ln["margin"] for ln in self.lines.values())
			/ sum(ln["revenue"] for ln in self.lines.values())
			* 100.0
		)
		self.assertAlmostEqual(weighted, exp, places=2)

	def test_occurrences_and_tcv_mixed_durations(self):
		# anual 24m Year/1 -> 2 ocurrencias; mensual 12m Month/1 -> 12; unico -> 1.
		self.assertEqual(self.lines["ANUAL"]["occurrences"], 2)
		self.assertEqual(self.lines["MENSUAL"]["occurrences"], 12)
		self.assertEqual(self.lines["UNICO"]["occurrences"], 1)
		# TCV ingreso por línea = ingreso_por_periodo * ocurrencias (sin inflar qty/rate).
		self.assertAlmostEqual(self.lines["ANUAL"]["revenue"], _sale_unit(100.0, 15.0) * 10 * 2, places=2)
		self.assertAlmostEqual(self.lines["MENSUAL"]["revenue"], _sale_unit(50.0, 25.0) * 15 * 12, places=2)
		self.assertAlmostEqual(self.lines["UNICO"]["revenue"], _sale_unit(200.0, 40.0) * 5, places=2)

	def test_cost_per_period(self):
		periods = self.m["periods"]
		# Mes 0: costo de las 3 (anual 1000 + mensual 750 + unico 1000) = 2750.
		self.assertAlmostEqual(periods[0]["external"], 1000.0 + 750.0 + 1000.0, places=2)
		# Mes 1..11: solo el mensual (750). Mes 12: solo el anual (1000); el mensual terminó su
		# compromiso de 12 meses en el Mes 11 (no se extiende ni se cuenta renovación).
		self.assertAlmostEqual(periods[1]["external"], 750.0, places=2)
		self.assertAlmostEqual(periods[12]["external"], 1000.0, places=2)

	def test_horizon_is_max_commitment(self):
		self.assertEqual(self.m["economic_horizon_months"], 24)


class TestCurrencyPresentation(unittest.TestCase):
	"""Regresión del fix de moneda: ``present_in_quote_currency`` convierte TODAS las secciones a la moneda
	de la cotización (incluidas **Trazabilidad temporal** y **segmentos del calendario**), dividiendo por el
	tipo de cambio nativo; es no-op si la cotización ya está en moneda base."""

	def _model(self, base_cur, quote_cur, rate):
		# Modelo mínimo con importes en BASE (200) en cada sección que la presentación debe convertir.
		return {
			"currency": base_cur,
			"base_currency": base_cur,
			"quote_currency": quote_cur,
			"rate_to_base": rate,
			"totals": {"revenue": 200.0, "total_cost": 150.0, "margin": 50.0, "margin_pct": 25.0},
			"periods": [{"revenue": 200.0, "external": 150.0, "revenue_components": [{"amount": 200.0}]}],
			"groups": {"MRC": {"revenue": 200.0, "lines": [{"revenue": 200.0}]}},
			"apu": {"unassigned_cost": 0.0},
			"financing": None,
			"temporal": [{"type": "Ingreso", "amount": 200.0}],
			"calendar_segments": [{"revenue": 200.0, "revenue_components": [{"amount": 200.0}]}],
		}

	def test_all_sections_in_quote_currency(self):
		from erpnext_proposals.erpnext_proposals.utils.economic_calendar import present_in_quote_currency

		m = present_in_quote_currency(self._model("MXN", "USD", 2.0))
		self.assertEqual(m["currency"], "USD")
		self.assertEqual(m["base_currency"], "MXN")
		# Todas las secciones divididas por el tipo de cambio (200/2 = 100):
		self.assertAlmostEqual(m["totals"]["revenue"], 100.0, places=2)
		self.assertAlmostEqual(m["periods"][0]["revenue"], 100.0, places=2)
		self.assertAlmostEqual(m["groups"]["MRC"]["revenue"], 100.0, places=2)
		self.assertAlmostEqual(m["temporal"][0]["amount"], 100.0, places=2)  # <- el bug corregido
		self.assertAlmostEqual(m["calendar_segments"][0]["revenue"], 100.0, places=2)  # <- el bug corregido
		self.assertAlmostEqual(m["calendar_segments"][0]["revenue_components"][0]["amount"], 100.0, places=2)
		# Los porcentajes NO se convierten.
		self.assertAlmostEqual(m["totals"]["margin_pct"], 25.0, places=2)

	def test_base_currency_is_noop(self):
		from erpnext_proposals.erpnext_proposals.utils.economic_calendar import present_in_quote_currency

		# Cotización ya en moneda base (quote == base) → sin conversión.
		m = present_in_quote_currency(self._model("MXN", "MXN", 1.0))
		self.assertAlmostEqual(m["temporal"][0]["amount"], 200.0, places=2)
		self.assertAlmostEqual(m["calendar_segments"][0]["revenue"], 200.0, places=2)
