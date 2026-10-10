# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Agrupación del costo laboral en el report «Profitability Estimate» (Rentabilidad Estimada):
por FASE cuando todas las filas tienen fase; por ITEM cuando falta alguna (Bloque 4 del rediseño
Project/Tasks). Prueba directa de `_build_report_rows` con datos ficticios, sin montar escenario."""

import unittest

from erpnext_proposals.erpnext_proposals.report.profitability_estimate.profitability_estimate import (
	_build_report_rows,
)

_TOTAL_KEYS = (
	"labor_hours",
	"labor_cost",
	"item_cost",
	"net_total",
	"taxes",
	"grand_total",
	"total_cost",
	"margin",
	"margin_pct",
)


def _lr(phase, item_code, title):
	return {
		"phase": phase,
		"item_code": item_code,
		"title": title,
		"designation": "",
		"hours": 1.0,
		"costing_rate": 0,
		"cost": 0,
		"notes": "",
	}


def _d(labor_rows):
	return {
		"quotation_meta": {"currency": "MXN"},
		"labor_rows": labor_rows,
		"item_cost_rows": [],
		"sales_rows": [],
		"totals": {k: 0 for k in _TOTAL_KEYS},
		"warnings": [],
		"qc_checks": [],
	}


class TestRentabilidadGrouping(unittest.TestCase):
	def test_groups_by_phase_when_all_rows_have_phase(self):
		# Con fase en todas las filas se agrupa por fase: NO aparece el item_code como header (ambas filas
		# comparten IT-A; si agrupara por Item habría un header "IT-A"). Robusto ante phase_label.
		from erpnext_proposals.erpnext_proposals.utils.phase import phase_label

		rows = _build_report_rows(_d([_lr("DISC", "IT-A", "a"), _lr("IMPL", "IT-A", "b")]))
		labels = [r.get("label") for r in rows]
		self.assertNotIn("IT-A", labels, "no debe agrupar por Item cuando hay fase")
		self.assertIn(phase_label("DISC"), labels)
		self.assertIn(phase_label("IMPL"), labels)

	def test_groups_by_item_when_no_row_has_phase(self):
		# NINGUNA fila tiene fase → fallback: headers por Item (item_code), nunca headers de fase.
		rows = _build_report_rows(_d([_lr("", "IT-A", "a"), _lr("", "IT-B", "b")]))
		labels = [r.get("label") for r in rows]
		self.assertIn("IT-A", labels)
		self.assertIn("IT-B", labels)

	def test_mixed_phase_keeps_phase_grouping(self):
		# Mixto (≥1 fila con fase): se CONSERVA la agrupación por fase; una fila sin fase NO fuerza
		# agrupación por Item (simplemente no recibe header de fase). Solo se agrupa por Item si NINGUNA
		# fila tiene fase.
		from erpnext_proposals.erpnext_proposals.utils.phase import phase_label

		rows = _build_report_rows(_d([_lr("DISC", "IT-A", "a"), _lr("", "IT-B", "b")]))
		labels = [r.get("label") for r in rows]
		self.assertIn(phase_label("DISC"), labels, "con ≥1 fase se agrupa por fase")
		self.assertNotIn("IT-A", labels, "no debe agrupar por Item en mixto")
		self.assertNotIn("IT-B", labels)
