"""Pruebas de `phase` como Link a Proposal Phase.

Cubre: Link válido acepta / valor inexistente rechaza, generación copia el Link, orden por
`Proposal Phase.sequence` (con orden alfabético del code distinto del sequence), impresión con
`phase_name` legible, y Scope Item sin fase.
"""

import unittest

import frappe
from frappe.exceptions import ValidationError

from erpnext_proposals.erpnext_proposals.report.profitability_estimate.profitability_estimate import (
	get_profitability_data,
)
from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.tests.phases import (
	cleanup_test_phases,
	ensure_test_phases,
)

TEMPLATE = "_Test Phase Template"
ITEM_P = "_Test Phase Item"


class TestPhaseLink(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._quotations = []
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_company

		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company found on test site.")
		cls._created_phases = ensure_test_phases()
		cls._created_fy = ensure_current_fiscal_year()
		cls._setup()

	@classmethod
	def tearDownClass(cls):
		for name in cls._quotations:
			if frappe.db.exists("Quotation", name):
				try:
					frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
				except Exception:
					pass
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_PHZ_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		cleanup_test_phases(getattr(cls, "_created_phases", None))
		cleanup_fiscal_year(getattr(cls, "_created_fy", None))
		super().tearDownClass()

	@classmethod
	def _setup(cls):
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		if not cg:
			raise unittest.SkipTest("No Customer Group found.")
		terr = frappe.db.get_value("Territory", {}, "name")
		if not frappe.db.exists("Customer", "_Test Phase Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test Phase Customer",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test Phase Customer"
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		ig = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		if not frappe.db.exists("Item", ITEM_P):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM_P,
					"item_name": ITEM_P,
					"item_group": ig,
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"is_sales_item": 1,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "t"}
			).insert(ignore_permissions=True)
		cls.cost_center = frappe.db.get_value("Cost Center", {"is_group": 0}, "name")

		# Scope Items: fases DISC(10)/IMPL(20)/GOLIVE(30) + uno sin fase.
		# El sequence del Scope Item NO refleja el orden de fase, para forzar que el orden
		# dependa de Proposal Phase.sequence.
		specs = [
			("_PHZ_1", "Levantamiento", "GOLIVE", 1),  # secuencia baja pero fase tardía
			("_PHZ_2", "Config", "DISC", 2),
			("_PHZ_3", "Capacitación", "IMPL", 3),
			("_PHZ_0", "Sin fase", None, 4),
		]
		for code, title, phase, seq in specs:
			if not frappe.db.exists("Scope Item", code):
				frappe.get_doc(
					{
						"doctype": "Scope Item",
						"code": code,
						"title": title,
						"sequence": seq,
						"erpnext_item": ITEM_P,
						"phase": phase,
						"estimated_hours": 5,
						"enabled": 1,
						"visible_in_proposal": 1,
					}
				).insert(ignore_permissions=True)

	def _make_quotation(self):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "PHZ-" + frappe.generate_hash(length=8),
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cost_center,
				"items": [{"item_code": ITEM_P, "item_name": ITEM_P, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self._quotations.append(doc.name)
		return doc

	# ── Tests ──

	def test_scope_item_accepts_valid_phase(self):
		si = frappe.get_doc("Scope Item", "_PHZ_2")
		self.assertEqual(si.phase, "DISC")

	def test_invalid_phase_rejected(self):
		with self.assertRaises(ValidationError):
			frappe.get_doc(
				{
					"doctype": "Scope Item",
					"code": "_PHZ_BAD",
					"title": "Inválida",
					"erpnext_item": ITEM_P,
					"phase": "NO_EXISTE_PHASE",
					"enabled": 1,
				}
			).insert(ignore_permissions=True)

	def test_generation_copies_link(self):
		q = self._make_quotation()
		by_code = {r.code: r for r in q.quotation_scope_items}
		self.assertEqual(by_code["_PHZ_2"].phase, "DISC")
		self.assertEqual(by_code["_PHZ_1"].phase, "GOLIVE")
		self.assertIn("_PHZ_0", by_code)  # sin fase generado sin error

	def test_scope_without_phase_ok(self):
		q = self._make_quotation()
		row = next(r for r in q.quotation_scope_items if r.code == "_PHZ_0")
		self.assertIn(row.phase, (None, ""))
		# Impresión no debe fallar por la fila sin fase
		html = frappe.get_print("Quotation", q.name, print_format="Propuesta Comercial")
		self.assertIn("Sin fase", html)

	def test_order_by_phase_sequence_not_alphabetical(self):
		q = self._make_quotation()
		data = get_profitability_data(q.name)
		phase_order = []
		for r in data["labor_rows"]:
			if r["phase"] and (not phase_order or phase_order[-1] != r["phase"]):
				if r["phase"] not in phase_order:
					phase_order.append(r["phase"])
		# Orden esperado por sequence: DISC(10) < IMPL(20) < GOLIVE(30)
		self.assertEqual(phase_order, ["DISC", "IMPL", "GOLIVE"])
		# NO el orden alfabético del code (DISC, GOLIVE, IMPL)
		self.assertNotEqual(phase_order, ["DISC", "GOLIVE", "IMPL"])

	def test_print_shows_phase_name_and_order(self):
		q = self._make_quotation()
		html = frappe.get_print("Quotation", q.name, print_format="Propuesta Comercial")
		# Muestra el phase_name legible, no el código
		self.assertIn("Descubrimiento", html)
		self.assertIn("Puesta en marcha", html)
		# Orden por sequence: Descubrimiento (DISC=10) antes que Puesta en marcha (GOLIVE=30)
		self.assertLess(html.index("Descubrimiento"), html.index("Puesta en marcha"))
