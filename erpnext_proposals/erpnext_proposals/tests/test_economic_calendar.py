# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Fase 2A — Evaluación Económica por periodos (ADR-0018). Datos 100% genéricos.

Dos bloques: (1) unitarios puros del motor (cadencia, ocurrencias, parseo de offset, distribución laboral)
sin BD; (2) integración sobre el site — resolver de comportamiento con precedencia Item>Item Group y
separación por Company, calendario relativo Mes 0…N (one_time / recurring / recurring comprable / Required
recurrente / infrastructure), plazo contractual default + override, y freeze (cambios de configuración tras
En Revisión no alteran la propuesta histórica). No re-captura precios: los importes salen de la propuesta.
"""

import json
import unittest

import frappe
from frappe.model.workflow import apply_workflow

from erpnext_proposals.erpnext_proposals.tests.company import (
	get_test_company,
	get_test_cost_center,
	get_test_item_group,
)
from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils.economic_calendar import (
	EconomicEvaluationError,
	_assert_reconciled,
	_assert_recurring_valid,
	_collapse_periods,
	_distribute_over_months,
	_labor_by_month,
	_occurrence_periods,
	_parse_offset_days,
	_step_months,
	get_economic_calendar,
	get_economic_evaluation,
	group_label,
)
from erpnext_proposals.erpnext_proposals.utils.quotation import _economic_behavior_for_item

TEMPLATE = "_EC Template"
ACT = "_EC Activity"
PHASE = "_EC_PHASE"
BPL = "_EC Buying PL"
GROUP_INFRA = "_EC Infra Group"
COMPANY_B = "_EC Co B"
COMPANY_B_ABBR = "_ECB"

IT_ONE = "_EC One"  # vendido no comprable, one_time
IT_REC = "_EC Rec"  # vendido no comprable, recurring
IT_REC_BUY = "_EC RecBuy"  # vendido comprable (buying 300), recurring → ingreso + costo externo recurrentes
IT_REQ_REC = "_EC ReqRec"  # requerido comprable (buying 200), recurring → costo recurrente sin ingreso
IT_INFRA = "_EC Infra"  # vendido en GROUP_INFRA (infrastructure)
IT_LAB = "_EC Lab"  # vendido sin scope de catálogo (para timeline laboral manual)

SC_MASTER = "_EC_SC_MASTER"  # scope maestro para filas de alcance manuales


# ───────────────────────────── Unitarios puros ─────────────────────────────


class TestEconomicEngine(unittest.TestCase):
	def test_step_months(self):
		self.assertEqual(_step_months("Month", 1), 1)
		self.assertEqual(_step_months("Month", 3), 3)
		self.assertEqual(_step_months("Year", 1), 12)
		self.assertEqual(_step_months("Week", 1), 1)  # sub-mensual -> mínimo 1 (cadencia YA validada)

	def test_recurring_config_validation(self):
		# Válidas: no lanzan.
		_assert_recurring_valid("Month", 1, 12, "X", None)
		_assert_recurring_valid("Month", 3, 12, "X", None)
		_assert_recurring_valid("Year", 1, 12, "X", None)
		# Inválidas: error explícito (nunca fallback a mensual).
		for interval, count, term in [
			("Fortnight", 1, 12),  # intervalo desconocido
			("", 1, 12),  # intervalo vacío
			(None, 1, 12),  # intervalo None
			("Month", 0, 12),  # count 0
			("Month", -2, 12),  # count negativo
			("Month", 1, 0),  # sin plazo (MRC requiere plazo)
			("Month", 1, None),  # plazo vacío
		]:
			with self.assertRaises(EconomicEvaluationError):
				_assert_recurring_valid(interval, count, term, "Componente X", None)

	def test_occurrence_periods(self):
		self.assertEqual(_occurrence_periods("one_time", 1, 12), [0])
		self.assertEqual(_occurrence_periods("infrastructure", 1, 12), [0])
		self.assertEqual(_occurrence_periods("recurring", 1, 12), list(range(12)))
		self.assertEqual(_occurrence_periods("recurring", 3, 12), [0, 3, 6, 9])  # trimestral
		self.assertEqual(_occurrence_periods("recurring", 1, 0), [0])  # sin plazo → un solo Mes 0

	def test_parse_offset_days(self):
		self.assertEqual(_parse_offset_days("0"), 0)
		self.assertEqual(_parse_offset_days("45"), 45)
		self.assertEqual(_parse_offset_days("30.9"), 30)
		self.assertEqual(_parse_offset_days("abc"), 0)  # defensivo (Data/string)
		self.assertEqual(_parse_offset_days(None), 0)
		self.assertEqual(_parse_offset_days(""), 0)

	def _scope_row(self, **kw):
		base = {
			"include_in_proposal": 1,
			"is_internal_cost_task": 0,
			"estimated_hours": 3,
			"costing_rate": 100,
			"rate_locked": 1,
			"planned_start_offset_days": "0",
			"planned_duration_days": 0,
			"is_milestone": 0,
		}
		base.update(kw)
		return frappe._dict(base)

	def _doc(self, rows):
		return frappe._dict(quotation_scope_items=rows)

	def test_labor_distribution_spread(self):
		# 3h x 100 = 300, offset 0, duración 60 días → 30/60 y 30/60 = 150 en Mes 0 y Mes 1.
		doc = self._doc([self._scope_row(planned_duration_days=60)])
		labor = _labor_by_month(doc, is_frozen=True)
		self.assertAlmostEqual(labor.get(0), 150.0)
		self.assertAlmostEqual(labor.get(1), 150.0)
		self.assertAlmostEqual(sum(labor.values()), 300.0)  # conserva el total

	def test_labor_milestone_point_cost(self):
		# milestone en offset 45 → Mes 1 puntual (floor(45/30)=1).
		doc = self._doc([self._scope_row(is_milestone=1, planned_start_offset_days="45")])
		labor = _labor_by_month(doc, is_frozen=True)
		self.assertEqual(labor, {1: 300.0})

	def test_labor_zero_duration_point_cost(self):
		doc = self._doc([self._scope_row(planned_duration_days=0, planned_start_offset_days="60")])
		labor = _labor_by_month(doc, is_frozen=True)
		self.assertEqual(labor, {2: 300.0})

	def test_labor_excludes_non_costable(self):
		doc = self._doc([self._scope_row(include_in_proposal=0, is_internal_cost_task=0)])
		self.assertEqual(_labor_by_month(doc, is_frozen=True), {})


# ───────────────────── Hardening: distribución / reconciliación / compactación (puros) ─────────────────


class TestEconomicHardeningPure(unittest.TestCase):
	# Timeline laboral: casos A-G (regla única _distribute_over_months). Ningún costo se pierde.
	def test_A_milestone_point(self):
		self.assertEqual(_distribute_over_months(0, 0, 1, 300.0), {0: 300.0})

	def test_A_zero_duration_point(self):
		self.assertEqual(_distribute_over_months(60, 0, 0, 300.0), {2: 300.0})

	def test_B_30_days(self):
		self.assertEqual(_distribute_over_months(0, 30, 0, 300.0), {0: 300.0})

	def test_C_60_days_split(self):
		d = _distribute_over_months(0, 60, 0, 300.0)
		self.assertEqual(sorted(d), [0, 1])
		self.assertAlmostEqual(d[0], 150.0)
		self.assertAlmostEqual(d[1], 150.0)
		self.assertAlmostEqual(sum(d.values()), 300.0)  # conserva total

	def test_D_45_days_crossing(self):
		# 45 días desde día 15: cubre día 15-59 → Mes 0 (15-29=15d) y Mes 1 (30-59=30d).
		d = _distribute_over_months(15, 45, 0, 450.0)
		self.assertEqual(sorted(d), [0, 1])
		self.assertAlmostEqual(d[0], 150.0)  # 15/45
		self.assertAlmostEqual(d[1], 300.0)  # 30/45
		self.assertAlmostEqual(sum(d.values()), 450.0)

	def test_E_offset_45_start_month1(self):
		d = _distribute_over_months(45, 0, 1, 500.0)  # hito en día 45 → Mes 1
		self.assertEqual(d, {1: 500.0})

	def test_F_offset_beyond_term_not_lost(self):
		# offset 400 días → Mes 13; el costo NO se pierde (mes calculado), aunque exceda un plazo de 12.
		d = _distribute_over_months(400, 0, 1, 700.0)
		self.assertEqual(d, {13: 700.0})
		self.assertAlmostEqual(sum(d.values()), 700.0)

	def test_G_duration_exceeds_term_spreads(self):
		# 720 días (24 meses) → reparto en 24 meses; suma conserva el total (no se descarta).
		d = _distribute_over_months(0, 720, 0, 2400.0)
		self.assertEqual(len(d), 24)
		self.assertAlmostEqual(sum(d.values()), 2400.0)

	# Reconciliación: falla explícita ante inconsistencia; nunca números silenciosos.
	def _good_model(self):
		periods = [
			{
				"period": 0,
				"revenue": 100.0,
				"external": 40.0,
				"labor": 10.0,
				"total_cost": 50.0,
				"margin": 50.0,
				"revenue_components": [{"amount": 100.0}],
				"external_components": [{"amount": 40.0}],
				"labor_components": [{"amount": 10.0}],
			}
		]
		return {
			"totals": {"revenue": 100.0, "external": 40.0, "labor": 10.0, "total_cost": 50.0, "margin": 50.0},
			"groups": {
				"NRC": {"revenue": 100.0, "external": 40.0, "labor": 10.0},
				"MRC": {"revenue": 0.0, "external": 0.0, "labor": 0.0},
				"CAPEX": {"revenue": 0.0, "external": 0.0, "labor": 0.0},
			},
			"periods": periods,
		}

	def test_reconcile_ok(self):
		_assert_reconciled(self._good_model())  # no lanza

	def test_reconcile_detects_group_mismatch(self):
		m = self._good_model()
		m["groups"]["NRC"]["revenue"] = 90.0  # descuadra grupos vs total
		with self.assertRaises(EconomicEvaluationError):
			_assert_reconciled(m)

	def test_reconcile_detects_calendar_mismatch(self):
		m = self._good_model()
		m["periods"][0]["revenue"] = 80.0  # calendario ≠ total
		with self.assertRaises(EconomicEvaluationError):
			_assert_reconciled(m)

	def test_reconcile_detects_trace_mismatch(self):
		m = self._good_model()
		m["periods"][0]["revenue_components"] = [{"amount": 70.0}]  # componentes ≠ periodo
		with self.assertRaises(EconomicEvaluationError):
			_assert_reconciled(m)

	# Compactación de PRESENTACIÓN: solo agrupa periodos realmente idénticos; rompe si cambia un flujo.
	def _p(self, period, rev, ext, lab):
		return {
			"period": period,
			"revenue": rev,
			"external": ext,
			"labor": lab,
			"total_cost": ext + lab,
			"margin": rev - ext - lab,
			"revenue_components": [],
			"external_components": [],
			"labor_components": [],
		}

	def test_collapse_non_uniform(self):
		# Mes 0, Mes 1, Meses 2-5 iguales, Mes 6 distinto, Meses 7-8 iguales.
		periods = [
			self._p(0, 100, 0, 50),
			self._p(1, 100, 0, 20),
			self._p(2, 100, 0, 0),
			self._p(3, 100, 0, 0),
			self._p(4, 100, 0, 0),
			self._p(5, 100, 0, 0),
			self._p(6, 100, 30, 0),
			self._p(7, 100, 0, 0),
			self._p(8, 100, 0, 0),
		]
		labels = [s["label"] for s in _collapse_periods(periods)]
		self.assertEqual(labels, ["Mes 0", "Mes 1", "Meses 2-5", "Mes 6", "Meses 7-8"])


# ───────────────────────────── Integración ─────────────────────────────────


class TestEconomicCalendar(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._quotations = []
		cls.company_a = get_test_company()
		if not cls.company_a:
			raise unittest.SkipTest("No Company on test site — run bench migrate first.")
		cls.company_b = cls._ensure_company_b()
		cls._fy = ensure_current_fiscal_year()
		ig = get_test_item_group()
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or frappe.db.get_value(
			"Territory", {}, "name"
		)
		if not cg:
			raise unittest.SkipTest("No Customer Group on test site.")
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		if not frappe.db.exists("Customer", "_EC Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_EC Customer",
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_EC Customer"
		cls.cc_a = get_test_cost_center(cls.company_a)
		cls.cc_b = get_test_cost_center(cls.company_b)

		if not frappe.db.exists("Activity Type", ACT):
			frappe.get_doc({"doctype": "Activity Type", "activity_type": ACT}).insert(ignore_permissions=True)
		frappe.db.set_value("Activity Type", ACT, "costing_rate", 100)

		if not frappe.db.exists("Proposal Phase", PHASE):
			frappe.get_doc(
				{
					"doctype": "Proposal Phase",
					"phase_code": PHASE,
					"phase_name": PHASE,
					"sequence": 10,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)

		if not frappe.db.exists("Item Group", GROUP_INFRA):
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": GROUP_INFRA,
					"parent_item_group": "All Item Groups",
					"is_group": 0,
				}
			).insert(ignore_permissions=True)

		# Buying Price List + Buying Settings (costo externo nativo, patrón Fase 1).
		if not frappe.db.exists("Price List", BPL):
			frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": BPL,
					"buying": 1,
					"selling": 0,
					"currency": "MXN",
				}
			).insert(ignore_permissions=True)
		cls._prev_bpl = frappe.db.get_single_value("Buying Settings", "buying_price_list")
		frappe.db.set_single_value("Buying Settings", "buying_price_list", BPL)

		def _item(code, sales, purchase, group=ig, buy_price=None):
			if not frappe.db.exists("Item", code):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_name": code,
						"item_group": group,
						"stock_uom": "Nos",
						"is_stock_item": 0,
						"is_sales_item": sales,
						"is_purchase_item": purchase,
					}
				).insert(ignore_permissions=True)
			if buy_price and not frappe.db.exists("Item Price", {"item_code": code, "price_list": BPL}):
				frappe.get_doc(
					{
						"doctype": "Item Price",
						"item_code": code,
						"price_list": BPL,
						"uom": "Nos",
						"price_list_rate": buy_price,
					}
				).insert(ignore_permissions=True)

		_item(IT_ONE, 1, 0)
		_item(IT_REC, 1, 0)
		_item(IT_REC_BUY, 1, 1, buy_price=300)
		_item(IT_REQ_REC, 0, 1, buy_price=200)
		_item(IT_INFRA, 1, 0, group=GROUP_INFRA)
		_item(IT_LAB, 1, 0)

		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "Test"}
			).insert(ignore_permissions=True)

		if not frappe.db.exists("Scope Item", SC_MASTER):
			frappe.get_doc(
				{
					"doctype": "Scope Item",
					"code": SC_MASTER,
					"title": SC_MASTER,
					"sequence": 10,
					"enabled": 1,
					"visible_in_proposal": 1,
					"estimated_hours": 0,
					"default_activity_type": ACT,
					"phase": PHASE,
				}
			).insert(ignore_permissions=True)

		cls._clear_all_settings()
		frappe.db.commit()  # nosemgrep — fixtures de test

	@classmethod
	def tearDownClass(cls):
		for name in cls._quotations:
			if frappe.db.exists("Quotation", name):
				doc = frappe.get_doc("Quotation", name)
				if doc.docstatus == 1:
					doc.flags.ignore_permissions = True
					try:
						doc.cancel()
					except Exception:
						pass
				frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
		if frappe.db.exists("Scope Item", SC_MASTER):
			frappe.delete_doc("Scope Item", SC_MASTER, force=True, ignore_permissions=True)
		cls._clear_all_settings()
		if getattr(cls, "_prev_bpl", None) is not None:
			frappe.db.set_single_value("Buying Settings", "buying_price_list", cls._prev_bpl)
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		frappe.db.commit()  # nosemgrep — limpieza de fixtures de test
		super().tearDownClass()

	def tearDown(self):
		self._clear_all_settings()

	# ── helpers ──────────────────────────────────────────────────────────
	@classmethod
	def _ensure_company_b(cls):
		if not frappe.db.exists("Company", COMPANY_B):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": COMPANY_B,
					"abbr": COMPANY_B_ABBR,
					"default_currency": "MXN",
					"country": "Mexico",
				}
			).insert(ignore_permissions=True)
		return COMPANY_B

	@classmethod
	def _clear_all_settings(cls):
		for company in (COMPANY_B, get_test_company()):
			name = frappe.db.get_value("Proposal Settings", {"company": company}, "name")
			if name:
				frappe.delete_doc("Proposal Settings", name, force=True, ignore_permissions=True)

	@staticmethod
	def _set_econ(company, rules=None, term=None):
		name = frappe.db.get_value("Proposal Settings", {"company": company}, "name")
		s = frappe.get_doc("Proposal Settings", name) if name else frappe.new_doc("Proposal Settings")
		s.company = company
		s.set("economic_behavior_rules", [])
		for source_type, source, behavior, interval, count in rules or []:
			s.append(
				"economic_behavior_rules",
				{
					"source_type": source_type,
					"source": source,
					"economic_behavior": behavior,
					"interval": interval,
					"interval_count": count,
				},
			)
		if term is not None:
			s.default_contract_term_months = term
		s.flags.ignore_permissions = True
		s.save(ignore_permissions=True)

	def _make_quotation(self, company, sold, term=None, scope_rows=None):
		cc = self.cc_a if company == self.company_a else self.cc_b
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "EC-" + frappe.generate_hash(length=8),
				"company": company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"workflow_state": "Borrador",
				"proposal_template": TEMPLATE,
				"proposal_cost_center": cc,
				"items": [
					{"item_code": c, "item_name": c, "qty": 1, "rate": 1000, "uom": "Nos"} for c in sold
				],
			}
		)
		if term is not None:
			doc.proposal_contract_term_months = term
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		if scope_rows:
			doc = frappe.get_doc("Quotation", doc.name)
			for r in scope_rows:
				doc.append("quotation_scope_items", r)
			doc.save(ignore_permissions=True)
		self.__class__._quotations.append(doc.name)
		return doc

	def _make_q_custom(self, company, lines, required=None, term=None, scope_rows=None):
		"""Quotation con líneas (item, qty, rate) explícitas — para bordes (qty decimal, precio 0, etc.)."""
		cc = self.cc_a if company == self.company_a else self.cc_b
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "ECH-" + frappe.generate_hash(length=8),
				"company": company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"workflow_state": "Borrador",
				"proposal_template": TEMPLATE,
				"proposal_cost_center": cc,
				"items": [
					{"item_code": it, "item_name": it, "qty": qty, "rate": rate, "uom": "Nos"}
					for (it, qty, rate) in lines
				],
				"required_items": [{"item": it, "qty": 1, "uom": "Nos"} for it in (required or [])],
			}
		)
		if term is not None:
			doc.proposal_contract_term_months = term
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		if scope_rows:
			doc = frappe.get_doc("Quotation", doc.name)
			for r in scope_rows:
				doc.append("quotation_scope_items", r)
			doc.save(ignore_permissions=True)
		self.__class__._quotations.append(doc.name)
		return doc

	def _transition(self, doc):
		wf = frappe.db.get_value("Workflow", {"document_type": "Quotation", "is_active": 1}, "name")
		action = frappe.db.get_value(
			"Workflow Transition", {"parent": wf, "state": "Borrador", "next_state": "En Revision"}, "action"
		)
		apply_workflow(doc, action)
		doc.reload()
		return doc

	def _cal(self, name):
		return get_economic_calendar(name)

	# ── resolver ─────────────────────────────────────────────────────────
	def test_01_no_rule_is_one_time(self):
		self.assertEqual(_economic_behavior_for_item(IT_REC, self.company_a), ("one_time", None, None))

	def test_02_item_rule_applies(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REC, "recurring", "Month", 1)])
		self.assertEqual(_economic_behavior_for_item(IT_REC, self.company_a), ("recurring", "Month", 1))

	def test_03_item_group_rule_applies(self):
		self._set_econ(self.company_a, rules=[("Item Group", GROUP_INFRA, "infrastructure", None, None)])
		self.assertEqual(_economic_behavior_for_item(IT_INFRA, self.company_a)[0], "infrastructure")

	def test_04_item_beats_item_group(self):
		self._set_econ(
			self.company_a,
			rules=[
				("Item", IT_INFRA, "recurring", "Month", 1),
				("Item Group", GROUP_INFRA, "infrastructure", None, None),
			],
		)
		self.assertEqual(_economic_behavior_for_item(IT_INFRA, self.company_a)[0], "recurring")

	def test_05_company_separation(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REC, "recurring", "Month", 1)])
		self.assertEqual(_economic_behavior_for_item(IT_REC, self.company_a)[0], "recurring")
		self.assertEqual(_economic_behavior_for_item(IT_REC, self.company_b), ("one_time", None, None))

	def test_06_no_settings_does_not_fail(self):
		# Company sin Proposal Settings → one_time, sin excepción.
		self.assertEqual(_economic_behavior_for_item(IT_REC, self.company_b), ("one_time", None, None))

	# ── calendario ───────────────────────────────────────────────────────
	def test_07_one_time_only_month_zero(self):
		q = self._make_quotation(self.company_a, sold=[IT_ONE], term=12)
		cal = self._cal(q.name)
		self.assertEqual(cal["periods"][0]["revenue"], 1000.0)
		self.assertTrue(all(p["revenue"] == 0.0 for p in cal["periods"][1:]))
		self.assertEqual(cal["totals"]["revenue"], 1000.0)

	def test_08_recurring_revenue_every_month(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REC, "recurring", "Month", 1)])
		q = self._make_quotation(self.company_a, sold=[IT_REC], term=12)
		cal = self._cal(q.name)
		self.assertEqual(cal["horizon"], 12)
		self.assertTrue(all(p["revenue"] == 1000.0 for p in cal["periods"]))
		self.assertEqual(cal["totals"]["revenue"], 12000.0)

	def test_09_recurring_purchasable_revenue_and_external(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REC_BUY, "recurring", "Month", 1)])
		q = self._make_quotation(self.company_a, sold=[IT_REC_BUY], term=12)
		cal = self._cal(q.name)
		self.assertEqual(cal["totals"]["revenue"], 12000.0)
		self.assertEqual(cal["totals"]["external"], 3600.0)  # 300 x 12
		self.assertTrue(all(p["external"] == 300.0 for p in cal["periods"]))

	def test_10_required_recurring_cost_no_revenue(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REQ_REC, "recurring", "Month", 1)])
		q = self._make_quotation(self.company_a, sold=[IT_ONE], term=12)
		doc = frappe.get_doc("Quotation", q.name)
		doc.append("required_items", {"item": IT_REQ_REC, "qty": 1, "uom": "Nos"})
		doc.save(ignore_permissions=True)
		cal = self._cal(q.name)
		self.assertEqual(cal["totals"]["external"], 2400.0)  # 200 x 12, sin ingreso del required
		self.assertEqual(cal["totals"]["revenue"], 1000.0)  # solo el IT_ONE vendido

	def test_11_infrastructure_is_one_time_in_2a(self):
		self._set_econ(self.company_a, rules=[("Item Group", GROUP_INFRA, "infrastructure", None, None)])
		q = self._make_quotation(self.company_a, sold=[IT_INFRA], term=12)
		cal = self._cal(q.name)
		self.assertEqual(cal["periods"][0]["revenue"], 1000.0)
		self.assertEqual(cal["totals"]["revenue"], 1000.0)  # tratado como one_time

	def test_12_quarterly_cadence(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REC, "recurring", "Month", 3)])
		q = self._make_quotation(self.company_a, sold=[IT_REC], term=12)
		cal = self._cal(q.name)
		months_with_revenue = [p["period"] for p in cal["periods"] if p["revenue"]]
		self.assertEqual(months_with_revenue, [0, 3, 6, 9])
		self.assertEqual(cal["totals"]["revenue"], 4000.0)

	# ── plazo contractual ────────────────────────────────────────────────
	def test_13_contract_term_default_from_settings(self):
		self._set_econ(self.company_a, term=24)
		q = self._make_quotation(self.company_a, sold=[IT_ONE])
		self.assertEqual(frappe.db.get_value("Quotation", q.name, "proposal_contract_term_months"), 24)

	def test_14_contract_term_manual_override(self):
		self._set_econ(self.company_a, term=24)
		q = self._make_quotation(self.company_a, sold=[IT_ONE], term=6)
		self.assertEqual(frappe.db.get_value("Quotation", q.name, "proposal_contract_term_months"), 6)

	def test_15_no_default_term_leaves_empty(self):
		q = self._make_quotation(self.company_b, sold=[IT_ONE])  # Company B sin settings
		self.assertIn(frappe.db.get_value("Quotation", q.name, "proposal_contract_term_months"), (0, None))

	# ── timeline laboral (integración) ───────────────────────────────────
	def test_16_labor_timeline_from_scope(self):
		q = self._make_quotation(
			self.company_a,
			sold=[IT_LAB],
			term=3,
			scope_rows=[
				{
					"scope_item": SC_MASTER,
					"item_code": IT_LAB,
					"estimated_hours": 3,
					"activity_type": ACT,
					"phase": PHASE,
					"include_in_proposal": 1,
					"planned_start_offset_days": "0",
					"planned_duration_days": 60,
				}
			],
		)
		cal = self._cal(q.name)
		self.assertAlmostEqual(cal["periods"][0]["labor"], 150.0)
		self.assertAlmostEqual(cal["periods"][1]["labor"], 150.0)
		self.assertAlmostEqual(cal["totals"]["labor"], 300.0)

	# ── freeze ───────────────────────────────────────────────────────────
	def test_17_draft_reflects_live_settings_change(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REC, "recurring", "Month", 1)])
		q = self._make_quotation(self.company_a, sold=[IT_REC], term=12)
		self.assertEqual(self._cal(q.name)["totals"]["revenue"], 12000.0)
		# cambiar a one_time en Draft → proyección cambia en vivo
		self._set_econ(self.company_a, rules=[("Item", IT_REC, "one_time", None, None)])
		self.assertEqual(self._cal(q.name)["totals"]["revenue"], 1000.0)

	def test_18_frozen_snapshot_ignores_later_settings(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REC, "recurring", "Month", 1)], term=12)
		q = self._make_quotation(self.company_a, sold=[IT_REC], term=12)
		doc = self._transition(frappe.get_doc("Quotation", q.name))
		self.assertEqual(doc.docstatus, 1)
		frozen_total = self._cal(q.name)["totals"]["revenue"]
		self.assertEqual(frozen_total, 12000.0)
		# la línea quedó con el snapshot congelado
		self.assertEqual(doc.items[0].proposal_economic_behavior, "recurring")
		# cambiar la configuración tras En Revisión NO altera la propuesta histórica
		self._set_econ(self.company_a, rules=[("Item", IT_REC, "one_time", None, None)])
		self.assertEqual(self._cal(q.name)["totals"]["revenue"], 12000.0)

	# ── modelo rico / presentación NRC-MRC-CAPEX ─────────────────────────
	def _full_rules(self):
		self._set_econ(
			self.company_a,
			rules=[
				("Item", IT_ONE, "one_time", None, None),
				("Item", IT_REC, "recurring", "Month", 1),
				("Item", IT_REC_BUY, "recurring", "Month", 1),
				("Item", IT_REQ_REC, "recurring", "Month", 1),
				("Item Group", GROUP_INFRA, "infrastructure", None, None),
			],
			term=12,
		)

	def _make_full(self):
		self._full_rules()
		q = self._make_quotation(
			self.company_a,
			sold=[IT_ONE, IT_REC, IT_REC_BUY, IT_INFRA],
			term=12,
			scope_rows=[
				{
					"scope_item": SC_MASTER,
					"item_code": IT_ONE,
					"estimated_hours": 10,
					"activity_type": ACT,
					"phase": PHASE,
					"include_in_proposal": 1,
					"planned_start_offset_days": "0",
					"planned_duration_days": 60,
				}
			],
		)
		doc = frappe.get_doc("Quotation", q.name)
		doc.append("required_items", {"item": IT_REQ_REC, "qty": 1, "uom": "Nos"})
		doc.save(ignore_permissions=True)
		return q.name

	def test_19_group_label_mapping(self):
		self.assertEqual(group_label("one_time"), "NRC")
		self.assertEqual(group_label("recurring"), "MRC")
		self.assertEqual(group_label("infrastructure"), "CAPEX")

	def test_20_evaluation_groups_classification(self):
		name = self._make_full()
		ev = get_economic_evaluation(name)
		nrc = {line["item_code"] for line in ev["groups"]["NRC"]["lines"]}
		mrc = {line["item_code"] for line in ev["groups"]["MRC"]["lines"]}
		capex = {line["item_code"] for line in ev["groups"]["CAPEX"]["lines"]}
		self.assertIn(IT_ONE, nrc)
		self.assertEqual(mrc, {IT_REC, IT_REC_BUY, IT_REQ_REC})
		self.assertIn(IT_INFRA, capex)

	def test_21_evaluation_summary_matches_calendar(self):
		name = self._make_full()
		ev = get_economic_evaluation(name)
		cal = get_economic_calendar(name)
		for k in ("revenue", "external", "labor", "total_cost", "margin"):
			self.assertAlmostEqual(ev["totals"][k], cal["totals"][k], msg=f"drift en {k}")

	def test_22_group_margins_sum_to_total(self):
		name = self._make_full()
		ev = get_economic_evaluation(name)
		g = ev["groups"]
		total = g["NRC"]["margin"] + g["MRC"]["margin"] + g["CAPEX"]["margin"]
		self.assertAlmostEqual(total, ev["totals"]["margin"])

	def test_23_mrc_line_contractual_accumulation(self):
		name = self._make_full()
		ev = get_economic_evaluation(name)
		rec = next(line for line in ev["groups"]["MRC"]["lines"] if line["item_code"] == IT_REC_BUY)
		self.assertEqual(rec["occurrences"], 12)
		self.assertEqual(rec["cadence"], "Mensual")
		self.assertAlmostEqual(rec["revenue"], rec["revenue_per_period"] * 12)
		self.assertAlmostEqual(rec["external"], rec["external_per_period"] * 12)

	def test_24_traceability_components_reconcile(self):
		name = self._make_full()
		ev = get_economic_evaluation(name)
		for p in ev["periods"]:
			self.assertAlmostEqual(sum(c["amount"] for c in p["revenue_components"]), p["revenue"])
			self.assertAlmostEqual(sum(c["amount"] for c in p["external_components"]), p["external"])
			self.assertAlmostEqual(sum(c["amount"] for c in p["labor_components"]), p["labor"])

	def test_25_effort_attributes_labor_to_item(self):
		name = self._make_full()
		ev = get_economic_evaluation(name)
		span = next(e for e in ev["effort"] if e["item_code"] == IT_ONE and e["cost"])
		self.assertEqual(span["periods"], [0, 1])  # 60 días desde Mes 0
		nrc_line = next(line for line in ev["groups"]["NRC"]["lines"] if line["item_code"] == IT_ONE)
		self.assertGreater(nrc_line["labor"], 0.0)  # labor atribuido al Item origen

	def test_26_frozen_evaluation_uses_snapshot(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REC, "recurring", "Month", 1)], term=12)
		q = self._make_quotation(self.company_a, sold=[IT_REC], term=12)
		self._transition(frappe.get_doc("Quotation", q.name))
		ev1 = get_economic_evaluation(q.name)
		self.assertEqual({line["item_code"] for line in ev1["groups"]["MRC"]["lines"]}, {IT_REC})
		# cambiar la regla tras En Revisión no reclasifica la propuesta histórica
		self._set_econ(self.company_a, rules=[("Item", IT_REC, "one_time", None, None)])
		ev2 = get_economic_evaluation(q.name)
		self.assertEqual({line["item_code"] for line in ev2["groups"]["MRC"]["lines"]}, {IT_REC})
		self.assertFalse(ev2["groups"]["NRC"]["lines"])  # no cayó a NRC

	# ── Hardening (integración) ──────────────────────────────────────────
	def test_27_determinism_full_structure(self):
		name = self._make_full()
		a = json.dumps(get_economic_evaluation(name), sort_keys=True, default=str)
		b = json.dumps(get_economic_evaluation(name), sort_keys=True, default=str)
		self.assertEqual(a, b)  # mismos inputs → estructura completa idéntica (no solo totales)

	def test_28_reconciliation_enforced(self):
		# get_economic_evaluation llama _assert_reconciled internamente: si retorna, reconcilió.
		ev = get_economic_evaluation(self._make_full())
		g = ev["groups"]
		self.assertAlmostEqual(
			g["NRC"]["revenue"] + g["MRC"]["revenue"] + g["CAPEX"]["revenue"], ev["totals"]["revenue"]
		)
		self.assertAlmostEqual(sum(p["revenue"] for p in ev["periods"]), ev["totals"]["revenue"])

	def test_29_external_source_traced(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REC_BUY, "recurring", "Month", 1)])
		q = self._make_quotation(self.company_a, sold=[IT_REC_BUY], term=12)
		ev = get_economic_evaluation(q.name)
		line = next(line for line in ev["groups"]["MRC"]["lines"] if line["item_code"] == IT_REC_BUY)
		self.assertEqual(line["origin"], "sold")
		self.assertEqual(line["external_source"], "buying_item_price")
		self.assertEqual(line["external_unit_cost"], 300.0)
		comp = ev["periods"][0]["external_components"][0]
		self.assertEqual(comp["source"], "buying_item_price")

	def test_30_labor_beyond_term_warns(self):
		# Scope con offset 400 días (Mes 13) y plazo 12 → warning explícito, sin pérdida de costo.
		q = self._make_quotation(
			self.company_a,
			sold=[IT_LAB],
			term=12,
			scope_rows=[
				{
					"scope_item": SC_MASTER,
					"item_code": IT_LAB,
					"estimated_hours": 5,
					"activity_type": ACT,
					"phase": PHASE,
					"include_in_proposal": 1,
					"planned_start_offset_days": "400",
					"planned_duration_days": 0,
					"is_milestone": 1,
				}
			],
		)
		ev = get_economic_evaluation(q.name)
		self.assertTrue(any(w["code"] == "labor_beyond_term" for w in ev["warnings"]))
		self.assertGreaterEqual(ev["horizon"], 14)  # Mes 0..13
		self.assertAlmostEqual(ev["totals"]["labor"], 500.0)  # costo NO perdido

	def test_31_effort_has_activity_and_profile(self):
		if not frappe.db.exists("Designation", "_EC Perfil"):
			frappe.get_doc({"doctype": "Designation", "designation_name": "_EC Perfil"}).insert(
				ignore_permissions=True
			)
		q = self._make_quotation(
			self.company_a,
			sold=[IT_LAB],
			term=3,
			scope_rows=[
				{
					"scope_item": SC_MASTER,
					"title": "Diseño de arquitectura",
					"item_code": IT_LAB,
					"estimated_hours": 10,
					"activity_type": ACT,
					"designation": "_EC Perfil",
					"phase": PHASE,
					"include_in_proposal": 1,
					"planned_start_offset_days": "0",
					"planned_duration_days": 0,
					"is_milestone": 1,
				}
			],
		)
		ev = get_economic_evaluation(q.name)
		e = next(e for e in ev["effort"] if e["cost"])
		self.assertEqual(e["activity"], "Diseño de arquitectura")
		self.assertEqual(e["designation"], "_EC Perfil")
		self.assertEqual(e["hours"], 10.0)
		self.assertEqual(e["rate"], 100.0)

	def test_32_edge_term_zero_and_empty(self):
		# El custom field bloquea plazo negativo (non_negative); probamos 0 y vacío (comportamiento seguro).
		for term in (0, None):
			q = self._make_q_custom(self.company_a, lines=[(IT_ONE, 1, 1000)], term=term)
			ev = get_economic_evaluation(q.name)  # no lanza; reconcilia
			self.assertGreaterEqual(ev["horizon"], 1)
			self.assertEqual(ev["totals"]["revenue"], 1000.0)

	def test_33_invalid_recurrence_errors(self):
		# Cadencia recurrente inválida → error explícito (no fallback a mensual).
		for interval, cnt in [("Month", 0), ("Month", -2), (None, 1)]:  # count 0/neg, intervalo vacío
			self._set_econ(self.company_a, rules=[("Item", IT_REC, "recurring", interval, cnt)])
			q = self._make_quotation(self.company_a, sold=[IT_REC], term=12)
			with self.assertRaises(EconomicEvaluationError):
				get_economic_evaluation(q.name)

	def test_33b_valid_recurrence_ok(self):
		for interval, cnt, expected in [("Month", 1, 12000.0), ("Month", 3, 4000.0), ("Year", 1, 1000.0)]:
			self._set_econ(self.company_a, rules=[("Item", IT_REC, "recurring", interval, cnt)])
			q = self._make_quotation(self.company_a, sold=[IT_REC], term=12)
			self.assertEqual(get_economic_evaluation(q.name)["totals"]["revenue"], expected)

	# ── MRC requiere plazo; NRC/CAPEX no (A-H) ───────────────────────────
	def test_37A_only_nrc_no_term_ok(self):
		q = self._make_q_custom(self.company_a, lines=[(IT_ONE, 1, 1000)], term=None)  # IT_ONE → one_time
		self.assertEqual(get_economic_evaluation(q.name)["totals"]["revenue"], 1000.0)

	def test_37B_only_capex_no_term_ok(self):
		self._set_econ(self.company_a, rules=[("Item Group", GROUP_INFRA, "infrastructure", None, None)])
		q = self._make_q_custom(self.company_a, lines=[(IT_INFRA, 1, 3000)], term=None)
		self.assertEqual(get_economic_evaluation(q.name)["totals"]["revenue"], 3000.0)

	def test_37C_nrc_capex_no_term_ok(self):
		self._set_econ(self.company_a, rules=[("Item Group", GROUP_INFRA, "infrastructure", None, None)])
		q = self._make_q_custom(self.company_a, lines=[(IT_ONE, 1, 1000), (IT_INFRA, 1, 3000)], term=None)
		self.assertEqual(get_economic_evaluation(q.name)["totals"]["revenue"], 4000.0)

	def test_37D_mrc_no_term_errors(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REC, "recurring", "Month", 1)])
		q = self._make_q_custom(self.company_a, lines=[(IT_REC, 1, 1000)], term=None)
		with self.assertRaises(EconomicEvaluationError):
			get_economic_evaluation(q.name)

	def test_37E_mrc_term_zero_errors(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REC, "recurring", "Month", 1)])
		q = self._make_q_custom(self.company_a, lines=[(IT_REC, 1, 1000)], term=0)
		with self.assertRaises(EconomicEvaluationError):
			get_economic_evaluation(q.name)

	def test_37F_mrc_valid_term_ok(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REC, "recurring", "Month", 1)])
		q = self._make_q_custom(self.company_a, lines=[(IT_REC, 1, 1000)], term=12)
		self.assertEqual(get_economic_evaluation(q.name)["totals"]["revenue"], 12000.0)

	def test_37G_required_mrc_no_term_errors(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REQ_REC, "recurring", "Month", 1)])
		q = self._make_q_custom(self.company_a, lines=[(IT_ONE, 1, 1000)], required=[IT_REQ_REC], term=None)
		with self.assertRaises(EconomicEvaluationError):
			get_economic_evaluation(q.name)

	def test_37H_sold_purchasable_mrc_no_term_errors(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REC_BUY, "recurring", "Month", 1)])
		q = self._make_q_custom(self.company_a, lines=[(IT_REC_BUY, 1, 2000)], term=None)
		with self.assertRaises(EconomicEvaluationError):
			get_economic_evaluation(q.name)

	# ── Plazo contractual vs horizonte económico ─────────────────────────
	def test_38_horizon_equals_term_when_scope_inside(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REC, "recurring", "Month", 1)])
		q = self._make_quotation(
			self.company_a,
			sold=[IT_REC],
			term=12,
			scope_rows=[
				{
					"scope_item": SC_MASTER,
					"item_code": IT_REC,
					"estimated_hours": 3,
					"activity_type": ACT,
					"phase": PHASE,
					"include_in_proposal": 1,
					"planned_start_offset_days": "0",
					"planned_duration_days": 30,  # Mes 0, dentro del plazo
				}
			],
		)
		ev = get_economic_evaluation(q.name)
		self.assertEqual(ev["economic_horizon_months"], 12)
		self.assertFalse([w for w in ev["warnings"] if w["code"] == "labor_beyond_term"])

	def test_39_horizon_extends_for_labor_not_revenue(self):
		self._set_econ(self.company_a, rules=[("Item", IT_REC, "recurring", "Month", 1)])
		q = self._make_quotation(
			self.company_a,
			sold=[IT_REC],  # MRC 1000/mes x 12 = 12000
			term=12,
			scope_rows=[
				{
					"scope_item": SC_MASTER,
					"item_code": IT_REC,
					"estimated_hours": 5,
					"activity_type": ACT,
					"phase": PHASE,
					"include_in_proposal": 1,
					"planned_start_offset_days": "390",  # Mes 13
					"planned_duration_days": 0,
					"is_milestone": 1,
				}
			],
		)
		ev = get_economic_evaluation(q.name)
		self.assertGreaterEqual(ev["economic_horizon_months"], 14)  # Mes 0..13
		self.assertTrue([w for w in ev["warnings"] if w["code"] == "labor_beyond_term"])
		# Ingresos MRC NO se extienden fuera del plazo: solo 12 periodos con ingreso.
		self.assertEqual(sum(1 for p in ev["periods"] if p["revenue"]), 12)
		self.assertEqual(ev["totals"]["revenue"], 12000.0)
		# Meses 12 y 13: solo costo laboral, sin ingreso → margen negativo.
		self.assertEqual(ev["periods"][13]["revenue"], 0.0)
		self.assertEqual(ev["periods"][13]["labor"], 500.0)
		self.assertLess(ev["periods"][13]["margin"], 0.0)
		# El calendario sigue reconciliando (invariantes no lanzaron).
		self.assertAlmostEqual(sum(p["labor"] for p in ev["periods"]), ev["totals"]["labor"])

	def test_40_nrc_no_term_scope_later_has_horizon(self):
		# Propuesta NRC sin plazo + Scope posterior: horizonte suficiente para mostrar el trabajo.
		q = self._make_q_custom(
			self.company_a,
			lines=[(IT_ONE, 1, 1000)],  # one_time
			term=None,
			scope_rows=[
				{
					"scope_item": SC_MASTER,
					"item_code": IT_ONE,
					"estimated_hours": 4,
					"activity_type": ACT,
					"phase": PHASE,
					"include_in_proposal": 1,
					"planned_start_offset_days": "90",  # Mes 3
					"planned_duration_days": 0,
					"is_milestone": 1,
				}
			],
		)
		ev = get_economic_evaluation(q.name)
		self.assertGreaterEqual(ev["economic_horizon_months"], 4)  # Mes 0..3
		self.assertEqual(ev["periods"][3]["labor"], 400.0)

	def test_34_edge_zero_price_and_revenue(self):
		# Precio 0 → ingreso 0; margen negativo si hay costo; margen % = 0 (sin división por cero).
		self._set_econ(self.company_a, rules=[("Item", IT_REQ_REC, "recurring", "Month", 1)])
		q = self._make_q_custom(self.company_a, lines=[(IT_ONE, 1, 0)], required=[IT_REQ_REC], term=12)
		ev = get_economic_evaluation(q.name)
		self.assertEqual(ev["totals"]["revenue"], 0.0)
		self.assertLess(ev["totals"]["margin"], 0.0)  # solo costo externo del required
		self.assertEqual(ev["totals"]["margin_pct"], 0.0)

	def test_35_precision_decimal(self):
		# qty 3 x 333.33 = 999.99; debe reconciliar dentro de tolerancia.
		q = self._make_q_custom(self.company_a, lines=[(IT_ONE, 3, 333.33)], term=6)
		ev = get_economic_evaluation(q.name)  # _assert_reconciled no lanza
		self.assertAlmostEqual(ev["totals"]["revenue"], 999.99, places=2)
		self.assertAlmostEqual(sum(p["revenue"] for p in ev["periods"]), ev["totals"]["revenue"], places=2)

	def test_36_freeze_ignores_item_price_change(self):
		# Costo externo congelado: cambiar el Item Price tras En Revisión no altera la evaluación histórica.
		self._set_econ(self.company_a, rules=[("Item", IT_REC_BUY, "recurring", "Month", 1)])
		q = self._make_quotation(self.company_a, sold=[IT_REC_BUY], term=12)
		self._transition(frappe.get_doc("Quotation", q.name))
		before = get_economic_evaluation(q.name)["totals"]["external"]
		ip = frappe.db.get_value("Item Price", {"item_code": IT_REC_BUY, "price_list": BPL}, "name")
		frappe.db.set_value("Item Price", ip, "price_list_rate", 900)
		after = get_economic_evaluation(q.name)["totals"]["external"]
		frappe.db.set_value("Item Price", ip, "price_list_rate", 300)  # restaurar
		self.assertEqual(before, 3600.0)
		self.assertEqual(after, 3600.0)  # histórico congelado


if __name__ == "__main__":
	unittest.main()
