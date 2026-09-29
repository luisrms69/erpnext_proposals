# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Handoff de compras (mínimo): la Task **Gestión de Compras** (materializada por el paquete
`default_procurement_package_item`) recibe una sección gestionada por la app que documenta las compras
previstas del alcance autorizado vigente. Datos ficticios. NO se tocan paquete/forecast/economía/addendas:
solo se verifica el enriquecimiento (idempotente) de `Task.description`.
"""

import unittest

import frappe
from frappe.tests import change_settings

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
from erpnext_proposals.erpnext_proposals.utils.procurement import (
	SECTION_END,
	SECTION_START,
	_procurement_task,
	refresh_procurement_task_description,
)
from erpnext_proposals.erpnext_proposals.utils.project import (
	apply_addendum_to_project,
	create_project_from_quotation,
)

TEMPLATE = "_PROC Template"
PHASE = "_PROC_PHASE"
ACT = "_PROC Activity"

IT_BUY = "_PROC Buy"  # vendido comprable (con scope propio visible) → aparece
IT_REQ_BUY = "_PROC ReqBuy"  # requerido comprable → aparece
IT_NOPUR = "_PROC NoPur"  # vendido NO comprable → NO aparece
IT_SKIP = "_PROC Skip"  # vendido comprable con proposal_skip_procurement → NO aparece
IT_B = "_PROC B"  # comprable para la addenda
IT_BUY_NS = "_PROC BuyNS"  # comprable SIN scope propio (dos ocurrencias sin doble atribución de labor)
PKG = "_PROC Pkg"  # paquete Gestión de Compras (no vendible/no comprable)

BUY_SCOPE = (
	"_PROC_BUY_SCOPE"  # scope visible del vendido (garantiza fila ejecutable sin depender del paquete)
)
PROC_SCOPE = "_PROC_PROC_SCOPE"  # scope interno del paquete → Task Gestión de Compras


class TestProcurementHandoff(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._q = []
		cls._p = []
		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company on test site — run bench migrate first.")
		cls._fy = ensure_current_fiscal_year()
		cls.cc = get_test_cost_center(cls.company)
		cls.price_list = get_test_price_list()
		ig = get_test_item_group()
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {}, "name")
		if not cg:
			raise unittest.SkipTest("No Customer Group on test site.")
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		if not frappe.db.exists("Customer", "_PROC Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_PROC Customer",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_PROC Customer"
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
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "t"}
			).insert(ignore_permissions=True)

		def _item(code, sales, purchase, skip=0):
			if not frappe.db.exists("Item", code):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_name": code,
						"item_group": ig,
						"stock_uom": "Nos",
						"is_stock_item": 0,
						"is_sales_item": sales,
						"is_purchase_item": purchase,
					}
				).insert(ignore_permissions=True)
			if skip:
				frappe.db.set_value("Item", code, "proposal_skip_procurement", 1)

		_item(IT_BUY, 1, 1)
		_item(IT_REQ_BUY, 0, 1)
		_item(IT_NOPUR, 1, 0)
		_item(IT_SKIP, 1, 1, skip=1)
		_item(IT_B, 1, 1)
		_item(IT_BUY_NS, 1, 1)
		_item(PKG, 0, 0)

		cls._make_scope(BUY_SCOPE, IT_BUY, visible=1, internal=0)
		cls._make_scope(PROC_SCOPE, PKG, visible=0, internal=1)
		cls._set_settings(procurement=PKG)
		frappe.db.commit()  # nosemgrep — fixtures de test

	@classmethod
	def tearDownClass(cls):
		for p in cls._p:
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
		for n in cls._q:
			if frappe.db.exists("Quotation", n):
				try:
					d = frappe.get_doc("Quotation", n)
					if d.docstatus == 1:
						d.flags.ignore_linked_doctypes = True
						d.cancel()
					frappe.delete_doc("Quotation", n, force=True, ignore_permissions=True)
				except Exception:
					pass
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_PROC_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		name = frappe.db.get_value("Proposal Settings", {"company": get_test_company()}, "name")
		if name:
			frappe.delete_doc("Proposal Settings", name, force=True, ignore_permissions=True)
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		frappe.db.commit()  # nosemgrep — limpieza de fixtures de test
		super().tearDownClass()

	# ── Helpers ───────────────────────────────────────────────────────────────
	@classmethod
	def _make_scope(cls, code, item, visible, internal):
		if frappe.db.exists("Scope Item", code):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Scope Item",
				"code": code,
				"title": code,
				"sequence": 10,
				"enabled": 1,
				"visible_in_proposal": visible,
				"is_internal_cost_task": internal,
				"estimated_hours": 1,
				"default_activity_type": ACT,
				"phase": PHASE,
				"erpnext_item": item,
			}
		).insert(ignore_permissions=True)

	@classmethod
	def _set_settings(cls, procurement=None):
		company = get_test_company()
		name = frappe.db.get_value("Proposal Settings", {"company": company}, "name")
		s = frappe.get_doc("Proposal Settings", name) if name else frappe.new_doc("Proposal Settings")
		s.company = company
		s.default_procurement_package_item = procurement
		s.flags.ignore_permissions = True
		s.save(ignore_permissions=True)

	def _quotation(self, sold, required=None, group=None, addendum=False, item_rows=None):
		rows = item_rows or [
			{"item_code": c, "item_name": c, "qty": 1, "rate": 1000, "uom": "Nos"} for c in sold
		]
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": group or ("PROC-" + frappe.generate_hash(length=8)),
				"company": self.company,
				"currency": "MXN",
				"selling_price_list": self.price_list,
				"transaction_date": frappe.utils.today(),
				"workflow_state": "Borrador",
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cc,
				"proposal_title": "PROC " + frappe.generate_hash(length=4),
				"items": rows,
				"required_items": [{"item": c, "qty": 25, "uom": "Nos"} for c in (required or [])],
			}
		)
		if addendum:
			doc.flags.from_addendum_creation = True
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._q.append(doc.name)
		return frappe.get_doc("Quotation", doc.name)

	def _win(self, doc):
		doc.reload()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		frappe.db.set_value("Quotation", doc.name, "workflow_state", "Ganada", update_modified=False)
		return frappe.get_doc("Quotation", doc.name)

	def _won_project(self, sold, required=None, item_rows=None):
		doc = self._win(self._quotation(sold, required=required, item_rows=item_rows))
		res = create_project_from_quotation(doc.name)
		self.__class__._p.append(res["project"])
		return doc, res["project"]

	def _proc_desc(self, project):
		task = _procurement_task(project)
		return task, (frappe.db.get_value("Task", task, "description") if task else None)

	# ── Tests ─────────────────────────────────────────────────────────────────
	def test_01_sold_purchasable_listed(self):
		_, proj = self._won_project([IT_BUY, IT_NOPUR])
		_, desc = self._proc_desc(proj)
		self.assertIn("Compras previstas", desc)
		self.assertIn(IT_BUY, desc)

	def test_02_required_purchasable_listed(self):
		_, proj = self._won_project([IT_BUY], required=[IT_REQ_BUY])
		_, desc = self._proc_desc(proj)
		self.assertIn(IT_REQ_BUY, desc)

	def test_03_non_purchasable_not_listed(self):
		_, proj = self._won_project([IT_BUY, IT_NOPUR])
		_, desc = self._proc_desc(proj)
		self.assertNotIn(IT_NOPUR, desc)

	def test_04_skip_not_listed(self):
		_, proj = self._won_project([IT_BUY, IT_SKIP])
		_, desc = self._proc_desc(proj)
		self.assertNotIn(IT_SKIP, desc)

	def test_05_package_not_listed_as_purchase(self):
		_, proj = self._won_project([IT_BUY])
		task, desc = self._proc_desc(proj)
		self.assertIsNotNone(task)
		# El paquete aparece como la Task, NUNCA como una compra prevista en la sección.
		section = desc.split(SECTION_START, 1)[1].split(SECTION_END, 1)[0]
		self.assertNotIn(PKG, section)

	@change_settings("Selling Settings", {"allow_multiple_items": 1})
	def test_06_two_occurrences_same_item_two_lines(self):
		# Item comprable SIN scope propio: dos ocurrencias vendidas del MISMO item_code. La fila ejecutable
		# la aporta el paquete (comportamiento vigente); el objetivo es verificar que la lista de compras
		# NO deduplica por item_code (dos ocurrencias = dos líneas).
		rows = [
			{"item_code": IT_BUY_NS, "item_name": IT_BUY_NS, "qty": 10, "rate": 1000, "uom": "Nos"},
			{"item_code": IT_BUY_NS, "item_name": IT_BUY_NS, "qty": 3, "rate": 1000, "uom": "Nos"},
		]
		_, proj = self._won_project([IT_BUY_NS], item_rows=rows)
		_, desc = self._proc_desc(proj)
		section = desc.split(SECTION_START, 1)[1].split(SECTION_END, 1)[0]
		self.assertEqual(section.count("<li>"), 2, "dos ocurrencias del mismo item_code = dos líneas")

	def test_07_qty_and_uom_shown(self):
		rows = [{"item_code": IT_BUY, "item_name": IT_BUY, "qty": 10, "rate": 1000, "uom": "Nos"}]
		_, proj = self._won_project([IT_BUY], required=[IT_REQ_BUY], item_rows=rows)
		_, desc = self._proc_desc(proj)
		self.assertIn("10 × " + IT_BUY, desc)  # noqa: RUF001
		self.assertIn("Nos", desc)
		self.assertIn("25 × " + IT_REQ_BUY, desc)  # noqa: RUF001  # qty del required

	def test_08_preserves_existing_description(self):
		_, proj = self._won_project([IT_BUY])
		task = _procurement_task(proj)
		# Texto legítimo previo FUERA de los marcadores.
		frappe.db.set_value(
			"Task",
			task,
			"description",
			"<p>LEGIT PM NOTE</p>" + (frappe.db.get_value("Task", task, "description") or ""),
		)
		refresh_procurement_task_description(proj)
		desc = frappe.db.get_value("Task", task, "description")
		self.assertIn("LEGIT PM NOTE", desc)
		self.assertIn("Compras previstas", desc)

	def test_09_second_refresh_no_duplicate(self):
		_, proj = self._won_project([IT_BUY])
		refresh_procurement_task_description(proj)
		refresh_procurement_task_description(proj)
		_, desc = self._proc_desc(proj)
		self.assertEqual(desc.count(SECTION_START), 1)
		self.assertEqual(desc.count(SECTION_END), 1)

	def test_10_project_creation_documents_section(self):
		_, proj = self._won_project([IT_BUY])
		task, desc = self._proc_desc(proj)
		self.assertIsNotNone(task)
		self.assertIn(SECTION_START, desc)
		self.assertIn(IT_BUY, desc)

	def test_11_addendum_additive_refresh_no_dup(self):
		root = self._win(self._quotation([IT_BUY]))
		res = create_project_from_quotation(root.name)
		proj = res["project"]
		self.__class__._p.append(proj)
		grp = f"{root.proposal_group}-ADD-01"
		add = self._win(self._quotation([IT_B], group=grp, addendum=True))
		apply_addendum_to_project(add.name, proj)
		_, desc = self._proc_desc(proj)
		self.assertIn(IT_BUY, desc)  # obligación de la raíz
		self.assertIn(IT_B, desc)  # alta de la addenda (aditivo)
		self.assertEqual(desc.count(SECTION_START), 1, "una sola sección, sin duplicar contenido")

	def test_12_no_package_is_safe_noop(self):
		self._set_settings(procurement=None)
		try:
			_, proj = self._won_project([IT_BUY])
			task = _procurement_task(proj)
			self.assertIsNone(task)  # sin paquete configurado → sin Task de compras
			self.assertIsNone(refresh_procurement_task_description(proj))  # no-op seguro
		finally:
			self._set_settings(procurement=PKG)  # restaurar para el resto de la clase
