"""Tests — guard de centro de costos (defecto crítico CC inconsistente).

Config nativa v16 (sin hooks nuevos): Company.cost_center vacío + Property Setters `reqd=1` en
`cost_center` de Sales Order Item / Purchase Order Item / Purchase Invoice Item (Sales Invoice Item ya
es reqd nativo). Objetivo: ningún renglón de SO/PO/PI puede quedar sin CC, y cuando hay Project el
sync de erpnext_proposals (`_sync_project_from_quotation`, hook `validate`) lo llena desde el Project
ANTES de la validación de obligatoriedad (`insert` corre `run_before_save_methods`→`validate` en
document.py:724 y recién después `_validate`→`_validate_mandatory` en 1067).

Cubre:
- Los 3 Property Setters dejan `cost_center` obligatorio (verificación de los fixtures).
- Herencia + ordenamiento: SO desde Quotation ganada con Company.cost_center vacío → el sync llena los
  renglones con el CC del Project y la SO guarda pese a `reqd`.
- Guard: una SO sin Project y sin CC explícito es rechazada con `MandatoryError`.
- Un CC explícito distinto NO es sobrescrito por el sync (solo llena si está vacío).
"""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.company import (
	get_test_company,
	get_test_cost_center,
	get_test_item_group,
	get_test_price_list,
)
from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.tests.phases import (
	cleanup_test_phases,
	ensure_test_phases,
)

TEMPLATE = "_CCG Template"
ITEM = "_CCG Item"
CUST = "_CCG Cust"
SUPP = "_CCG Supp"
SCOPE = "_CCG_S1"
REQD_DOCTYPES = ("Sales Order Item", "Purchase Order Item", "Purchase Invoice Item")


class TestCostCenterGuard(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._q = []
		cls._so = []
		cls._po = []
		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company on test site.")
		cls._phases = ensure_test_phases()
		cls._fy = ensure_current_fiscal_year()
		cls.price_list = get_test_price_list()
		cls.cc = get_test_cost_center(cls.company)
		# Segundo CC hoja distinto, para probar que un CC explícito no se sobrescribe.
		cls.cc2 = cls._ensure_second_cost_center()
		cls.uom = frappe.db.get_value("UOM", {"enabled": 1}, "name")
		if not cls.uom:
			raise unittest.SkipTest("No enabled UOM on test site.")
		ig = get_test_item_group()
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {}, "name")
		if not cg:
			raise unittest.SkipTest("No Customer Group on test site.")
		if not frappe.db.exists("Customer", CUST):
			frappe.get_doc(
				{"doctype": "Customer", "customer_name": CUST, "customer_group": cg, "territory": terr}
			).insert(ignore_permissions=True)
		sg = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name") or frappe.db.get_value(
			"Supplier Group", {}, "name"
		)
		if sg and not frappe.db.exists("Supplier", SUPP):
			frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": SUPP,
					"supplier_group": sg,
					"default_currency": "MXN",  # misma moneda que la Company → conversion_rate = 1
				}
			).insert(ignore_permissions=True)
		if frappe.db.exists("Supplier", SUPP):
			# Normaliza la moneda (un Supplier preexistente pudo quedar en otra) → conversion_rate = 1.
			frappe.db.set_value("Supplier", SUPP, "default_currency", "MXN")
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": ITEM,
					"item_group": ig,
					"stock_uom": cls.uom,
					"is_stock_item": 0,
					"is_sales_item": 1,
					"is_purchase_item": 1,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "t"}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Scope Item", SCOPE):
			frappe.get_doc(
				{
					"doctype": "Scope Item",
					"code": SCOPE,
					"title": SCOPE,
					"sequence": 1,
					"erpnext_item": ITEM,
					"estimated_hours": 4,
					"enabled": 1,
					"visible_in_proposal": 1,
					"phase": "DISC",
				}
			).insert(ignore_permissions=True)
		# Vaciar el default de CC de la Company → los renglones nacen sin CC (reproduce el fix en ACE).
		cls._orig_company_cc = frappe.db.get_value("Company", cls.company, "cost_center")
		frappe.db.set_value("Company", cls.company, "cost_center", "")

	@classmethod
	def _ensure_second_cost_center(cls):
		existing = frappe.db.get_value(
			"Cost Center", {"is_group": 0, "company": cls.company, "cost_center_name": "_CCG Alt"}, "name"
		)
		if existing:
			return existing
		parent = frappe.db.get_value("Cost Center", {"is_group": 1, "company": cls.company}, "name")
		return (
			frappe.get_doc(
				{
					"doctype": "Cost Center",
					"cost_center_name": "_CCG Alt",
					"company": cls.company,
					"parent_cost_center": parent,
					"is_group": 0,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	@classmethod
	def tearDownClass(cls):
		frappe.db.set_value("Company", cls.company, "cost_center", cls._orig_company_cc or "")
		for n in cls._po:
			if frappe.db.exists("Purchase Order", n):
				try:
					d = frappe.get_doc("Purchase Order", n)
					if d.docstatus == 1:
						d.flags.ignore_linked_doctypes = True
						d.cancel()
					frappe.delete_doc("Purchase Order", n, force=True, ignore_permissions=True)
				except Exception:
					pass
		for n in cls._so:
			if frappe.db.exists("Sales Order", n):
				try:
					d = frappe.get_doc("Sales Order", n)
					if d.docstatus == 1:
						d.flags.ignore_linked_doctypes = True
						d.cancel()
					frappe.delete_doc("Sales Order", n, force=True, ignore_permissions=True)
				except Exception:
					pass
		for n in cls._q:
			p = frappe.db.get_value("Quotation", n, "proposal_project")
			if p:
				for t in frappe.get_all("Task", filters={"project": p}, pluck="name"):
					try:
						frappe.delete_doc("Task", t, force=True, ignore_permissions=True)
					except Exception:
						pass
				if frappe.db.exists("Project", p):
					try:
						frappe.delete_doc("Project", p, force=True, ignore_permissions=True)
					except Exception:
						pass
			if frappe.db.exists("Quotation", n):
				try:
					d = frappe.get_doc("Quotation", n)
					if d.docstatus == 1:
						d.flags.ignore_linked_doctypes = True
						d.cancel()
					frappe.delete_doc("Quotation", n, force=True, ignore_permissions=True)
				except Exception:
					pass
		if frappe.db.exists("Scope Item", SCOPE):
			frappe.delete_doc("Scope Item", SCOPE, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		cleanup_test_phases(getattr(cls, "_phases", None))
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		super().tearDownClass()

	# ── Helpers ──────────────────────────────────────────────────────────────

	def _won_quotation(self):
		from erpnext_proposals.erpnext_proposals.utils.project import auto_create_project_on_won

		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": CUST,
				"proposal_group": "CCG-" + frappe.generate_hash(length=6),
				"company": self.company,
				"currency": "MXN",
				"selling_price_list": self.price_list,
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cc,
				"proposal_title": "CCG " + frappe.generate_hash(length=4),
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": self.uom}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._q.append(doc.name)
		doc.reload()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		frappe.db.set_value("Quotation", doc.name, "workflow_state", "Ganada", update_modified=False)
		auto_create_project_on_won(doc.name)
		return doc.name

	def _sales_order_from(self, quotation):
		from erpnext.selling.doctype.quotation.quotation import make_sales_order

		so = make_sales_order(quotation)
		so.delivery_date = frappe.utils.today()
		for it in so.items:
			it.delivery_date = frappe.utils.today()
		return so

	# ── Tests ────────────────────────────────────────────────────────────────

	def test_1_property_setters_make_cost_center_reqd(self):
		"""Los 3 Property Setters (fixtures) dejan `cost_center` obligatorio en los renglones."""
		frappe.clear_cache()
		for dt in REQD_DOCTYPES:
			f = frappe.get_meta(dt).get_field("cost_center")
			self.assertIsNotNone(f, f"{dt} sin campo cost_center")
			self.assertEqual(f.reqd, 1, f"{dt}.cost_center debe ser reqd=1 (Property Setter)")
		# Sales Invoice Item ya es reqd nativo (no lo tocamos, pero debe seguir reqd).
		sii = frappe.get_meta("Sales Invoice Item").get_field("cost_center")
		self.assertEqual(sii.reqd, 1, "Sales Invoice Item.cost_center debe seguir reqd (nativo)")

	def test_2_sync_fills_project_cost_center_before_mandatory(self):
		"""Company default vacío + Project → el sync llena el CC de los renglones antes del `reqd`:
		la SO guarda y hereda el CC del Project (header y renglones)."""
		q = self._won_quotation()
		project = frappe.db.get_value("Quotation", q, "proposal_project")
		self.assertTrue(project, "la quotation ganada debe tener Project")
		project_cc = frappe.db.get_value("Project", project, "cost_center")
		self.assertEqual(project_cc, self.cc, "el Project debe heredar el proposal_cost_center")

		so = self._sales_order_from(q)
		# Sin ignore_mandatory: si el guard rompiera el flujo legítimo, esto lanzaría MandatoryError.
		so.insert(ignore_permissions=True)
		self.__class__._so.append(so.name)

		self.assertEqual(so.project, project, "la SO debe quedar ligada al Project (sync)")
		self.assertEqual(so.cost_center, self.cc, "el header de la SO hereda el CC del Project")
		for it in so.items:
			self.assertEqual(it.cost_center, self.cc, f"renglón {it.item_code} hereda el CC del Project")

	def test_3_guard_blocks_line_without_cost_center(self):
		"""SO sin Project y sin CC explícito (Company default vacío) → rechazada por `reqd`."""
		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"quotation_to": "Customer",
				"party_name": CUST,
				"company": self.company,
				"currency": "MXN",
				"selling_price_list": self.price_list,
				"transaction_date": frappe.utils.today(),
				"delivery_date": frappe.utils.today(),
				"items": [
					{
						"item_code": ITEM,
						"item_name": ITEM,
						"qty": 1,
						"rate": 1000,
						"uom": self.uom,
						"delivery_date": frappe.utils.today(),
					}
				],
			}
		)
		with self.assertRaises(frappe.MandatoryError):
			so.insert(ignore_permissions=True)

	def test_4_explicit_cost_center_not_overwritten(self):
		"""Un CC explícito y distinto en el renglón NO es sobrescrito por el sync (solo llena si vacío)."""
		q = self._won_quotation()
		so = self._sales_order_from(q)
		for it in so.items:
			it.cost_center = self.cc2  # CC explícito distinto al del Project
		so.insert(ignore_permissions=True)
		self.__class__._so.append(so.name)
		for it in so.items:
			self.assertEqual(it.cost_center, self.cc2, "el sync no debe pisar un CC explícito del renglón")

	def test_5_cost_center_propagates_so_to_si_and_po(self):
		"""Propagación desde la SO: el CC del Project (heredado en la SO) se transfiere a la Sales
		Invoice (make_sales_invoice lo FUERZA + reqd nativo) y a la Purchase Order (copia textual del
		renglón: cost_center no está en el field_no_map del mapeo). PO→PI usa el mismo mecanismo de copia
		verbatim (cost_center ausente del field_no_map de make_purchase_invoice)."""
		if not frappe.db.exists("Supplier", SUPP):
			raise unittest.SkipTest("No Supplier Group on test site.")
		from erpnext.selling.doctype.sales_order.sales_order import (
			make_purchase_order,
			make_sales_invoice,
		)

		q = self._won_quotation()
		so = self._sales_order_from(q)
		so.insert(ignore_permissions=True)
		self.__class__._so.append(so.name)
		so.submit()

		# SO → Sales Invoice: make_sales_invoice fuerza cost_center = Project.cost_center.
		si = make_sales_invoice(so.name)
		for it in si.items:
			self.assertEqual(it.cost_center, self.cc, "SI hereda el CC del Project (forzado)")

		# SO → Purchase Order: cost_center NO está en field_no_map → se copia textual del renglón de la
		# SO. make_purchase_order exige `selected_items` y auto-inserta la PO (una por proveedor).
		selected = [{"name": it.name, "item_code": it.item_code, "supplier": SUPP} for it in so.items]
		pos = make_purchase_order(so.name, selected_items=selected)
		self.assertTrue(pos, "make_purchase_order debe devolver al menos una PO")
		po = pos[0]
		self.__class__._po.append(po.name)
		for it in po.items:
			self.assertEqual(it.cost_center, self.cc, "PO hereda el CC de la SO (copia verbatim)")


if __name__ == "__main__":
	unittest.main()
