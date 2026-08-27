"""Snapshot del campo `moment` (momento relativo de ejecución) del Scope Item → Quotation Scope Item.

Verifica el patrón de congelado (igual que la planeación PMO): al generar el alcance de una Quotation,
`moment` se copia como snapshot comercial; el resync explícito lo refresca desde el catálogo; y los
Scope Items sin `moment` no rompen (queda vacío, sin inventar valor).

Datos ficticios; nunca contenido de cliente.
"""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils.quotation import resync_scope_from_catalog

TEMPLATE = "_Test MOMENT Template"
ITEM = "_Test MOMENT Item"
PHASE = "_MOMP1"


class TestScopeMomentSnapshot(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from erpnext_proposals.erpnext_proposals.tests.company import (
			get_test_company,
			get_test_item_group,
			get_test_price_list,
		)

		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company found on test site.")
		cls._quotations = []
		cls._created_fy = ensure_current_fiscal_year()
		if not frappe.db.exists("Proposal Phase", PHASE):
			frappe.get_doc(
				{
					"doctype": "Proposal Phase",
					"phase_code": PHASE,
					"phase_name": "Fase moment",
					"sequence": 10,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {}, "name")
		if not frappe.db.exists("Customer", "_Test MOMENT Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test MOMENT Customer",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test MOMENT Customer"
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		ig = get_test_item_group()
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": ITEM,
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
		# Price List de venta explícita (MXN): el site fresco de CI no siembra ninguna → sin esto el
		# save() sin ignore_mandatory falla por selling_price_list/price_list_currency. Se setea en la
		# Quotation (ver _draft), no por default del site.
		cls.selling_price_list = get_test_price_list()
		# Dos scope items: uno CON moment, otro SIN moment (no debe romper).
		cls._scope("_MOM_S1", 10, "Periodo 2-3")
		cls._scope("_MOM_S2", 20, None)

	@classmethod
	def _scope(cls, code, seq, moment):
		if frappe.db.exists("Scope Item", code):
			return
		frappe.get_doc(
			{
				"doctype": "Scope Item",
				"code": code,
				"title": code,
				"sequence": seq,
				"erpnext_item": ITEM,
				"phase": PHASE,
				"enabled": 1,
				"visible_in_proposal": 1,
				"estimated_hours": 4,
				"moment": moment,
			}
		).insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		for name in cls._quotations:
			if frappe.db.exists("Quotation", name):
				try:
					frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
				except Exception:
					pass
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_MOM_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Phase", PHASE):
			frappe.delete_doc("Proposal Phase", PHASE, force=True, ignore_permissions=True)
		cleanup_fiscal_year(getattr(cls, "_created_fy", None))
		super().tearDownClass()

	def _draft(self):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "MOM-" + frappe.generate_hash(length=6),
				"company": self.company,
				"currency": "MXN",
				"selling_price_list": self.selling_price_list,
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cost_center,
				"proposal_title": "MOM " + frappe.generate_hash(length=4),
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._quotations.append(doc.name)
		return frappe.get_doc("Quotation", doc.name)

	def _moment_of(self, doc, code):
		for r in doc.quotation_scope_items:
			if r.code == code:
				return r.moment
		return "__missing__"

	def test_moment_frozen_on_generation(self):
		doc = self._draft()
		self.assertEqual(self._moment_of(doc, "_MOM_S1"), "Periodo 2-3")
		# Scope Item sin moment → snapshot vacío (None/""), nunca inventado.
		self.assertIn(self._moment_of(doc, "_MOM_S2"), (None, ""))

	def test_resync_refreshes_moment(self):
		doc = self._draft()
		# Simula un valor viejo en la fila y confirma que el resync lo restaura desde el catálogo.
		for r in doc.quotation_scope_items:
			if r.code == "_MOM_S1":
				r.moment = "valor viejo"
		doc.save(ignore_permissions=True)
		frappe.db.set_value("Quotation", doc.name, "workflow_state", "Borrador", update_modified=False)
		resync_scope_from_catalog(doc.name)
		doc.reload()
		self.assertEqual(self._moment_of(doc, "_MOM_S1"), "Periodo 2-3")
