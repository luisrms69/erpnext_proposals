"""Regresión: el warning de costeo (`_warn_non_blocking`) NO debe exigir Activity Type cuando existe
una tarifa GENERAL válida por Designation.

- El motor (`get_designation_cost`) resuelve por tarifa general de la Designation sin Activity Type.
- `_warn_non_blocking` debe marcar "costo laboral incompleto" solo cuando NINGUNA fuente resuelve tarifa.
- Valida el escenario DEMO: 500/650/800 con Activity Type vacío → costo total 192,800 (PMO 36 h = 28,800).
"""

import unittest

import frappe
from frappe.utils import flt

from erpnext_proposals.erpnext_proposals.utils.cost_matrix import get_designation_cost
from erpnext_proposals.erpnext_proposals.utils.workflow_validations import _warn_non_blocking

D_APPS = "_WT CONSULTOR APPS"
D_DEV = "_WT DESARROLLADOR"
D_PMO = "_WT MANAGER PMO"
D_NORATE = "_WT SIN TARIFA"
RATES = {D_APPS: 500, D_DEV: 650, D_PMO: 800}
INCOMPLETO = "costo laboral incompleto"


class TestWarnCostingDesignationRate(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._cm = []
		for d in (D_APPS, D_DEV, D_PMO, D_NORATE):
			if not frappe.db.exists("Designation", d):
				frappe.get_doc({"doctype": "Designation", "designation_name": d}).insert(
					ignore_permissions=True
				)
		# Tarifa GENERAL válida (is_general_rate=1, status=ok) para 3 designations; D_NORATE sin tarifa.
		for d, rate in RATES.items():
			row = frappe.get_doc(
				{
					"doctype": "Proposal Cost Matrix",
					"designation": d,
					"is_general_rate": 1,
					"avg_costing_rate": rate,
					"status": "ok",
					"notes": "_WT",
				}
			).insert(ignore_permissions=True)
			cls._cm.append(row.name)

	@classmethod
	def tearDownClass(cls):
		for n in cls._cm:
			if frappe.db.exists("Proposal Cost Matrix", n):
				frappe.delete_doc("Proposal Cost Matrix", n, force=True, ignore_permissions=True)
		for d in (D_APPS, D_DEV, D_PMO, D_NORATE):
			if frappe.db.exists("Designation", d):
				try:
					frappe.delete_doc("Designation", d, force=True, ignore_permissions=True)
				except Exception:
					pass
		super().tearDownClass()

	# ── helpers ──────────────────────────────────────────────────────────────
	def _row(self, desig, hours, internal=False, activity=None):
		return frappe._dict(
			include_in_proposal=(0 if internal else 1),
			is_internal_cost_task=(1 if internal else 0),
			designation=desig,
			activity_type=activity,
			estimated_hours=hours,
		)

	def _capture_warn(self, rows):
		doc = frappe._dict(company=None, currency="MXN", quotation_scope_items=rows)
		captured = []
		orig = frappe.msgprint
		frappe.msgprint = lambda *a, **k: captured.append(a[0] if a else k.get("msg", ""))
		try:
			_warn_non_blocking(doc)
		finally:
			frappe.msgprint = orig
		return " ".join(str(c) for c in captured)

	# ── tests ────────────────────────────────────────────────────────────────
	def test_general_rate_resolves_without_activity_type(self):
		"""El motor resuelve la tarifa general de la Designation con Activity Type vacío."""
		rate, source = get_designation_cost(D_PMO, None)
		self.assertEqual(flt(rate), 800.0)
		self.assertEqual(source, "matrix_general")

	def test_scenario_total_192800_and_no_false_warning(self):
		"""Escenario DEMO completo: 4 vendibles + 3 PMO internas, Activity Type vacío en todas."""
		rows = [
			self._row(D_APPS, 56),
			self._row(D_APPS, 64),
			self._row(D_DEV, 120),
			self._row(D_DEV, 40),
			self._row(D_PMO, 8, internal=True),
			self._row(D_PMO, 8, internal=True),
			self._row(D_PMO, 20, internal=True),
		]
		# Costo laboral como lo calcula el reporte: hours * get_designation_cost (sin Activity Type).
		total = sum(
			flt(r.estimated_hours) * flt(get_designation_cost(r.designation, r.activity_type)[0])
			for r in rows
		)
		self.assertEqual(total, 192800.0)
		pmo = sum(flt(r.estimated_hours) * 800 for r in rows if r.designation == D_PMO)
		self.assertEqual(pmo, 28800.0)
		# Sin warning falso: todas las designations tienen tarifa general aunque Activity Type esté vacío.
		self.assertNotIn(INCOMPLETO, self._capture_warn(rows))

	def test_warning_when_designation_has_no_rate(self):
		"""Fila cuya Designation no tiene tarifa resoluble → SÍ marca costo incompleto."""
		rows = [self._row(D_APPS, 10), self._row(D_NORATE, 10)]
		self.assertIn(INCOMPLETO, self._capture_warn(rows))

	def test_internal_cost_row_evaluated(self):
		"""Las filas internas de costo (is_internal_cost_task) también se evalúan."""
		self.assertIn(INCOMPLETO, self._capture_warn([self._row(D_NORATE, 8, internal=True)]))
		self.assertNotIn(INCOMPLETO, self._capture_warn([self._row(D_PMO, 8, internal=True)]))


if __name__ == "__main__":
	unittest.main()
