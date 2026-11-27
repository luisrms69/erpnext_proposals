# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — asignación automática de responsable (`Scope Item.default_assignee`).

Cubre: Scope Item con responsable → Task hija asignada nativamente (ToDo + `_assign`); Scope Item sin
responsable → Task hija sin asignar; Task padre (`is_group`) nunca asignada; Task operativa «Entregar» (Item
vendido sin alcance) nunca asignada; reintento de `create_project_from_quotation` no duplica ToDos ni
asignaciones. Reutiliza el harness de integración Project/Task.
"""

import json
import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.tests.phases import (
	cleanup_test_phases,
	ensure_test_phases,
)
from erpnext_proposals.erpnext_proposals.utils.project import create_project_from_quotation

TEMPLATE = "_Test SA Template"
ITEM_WA = "_Test SA Item With Scope"
ITEM_NOSCOPE = "_Test SA Item NoScope"
ASSIGNEE = "_sa_assignee@example.com"
UOM = "_Test UOM"  # UOM estándar de Frappe (habilitada en el site de pruebas); no dependemos de 'Nos'.


class TestScopeAssignee(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._quotations = []
		cls._projects = []
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_company

		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company found on test site.")
		cls._created_phases = ensure_test_phases()
		cls._created_fy = ensure_current_fiscal_year()
		cls._setup()

	@classmethod
	def _setup(cls):
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_item_group

		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		if not cg:
			raise unittest.SkipTest("No Customer Group found.")
		terr = frappe.db.get_value("Territory", {}, "name")
		if not frappe.db.exists("Customer", "_Test SA Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test SA Customer",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test SA Customer"
		if not frappe.db.exists("User", ASSIGNEE):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": ASSIGNEE,
					"first_name": "SA Assignee",
					"send_welcome_email": 0,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		ig = get_test_item_group()
		for code in (ITEM_WA, ITEM_NOSCOPE):
			if not frappe.db.exists("Item", code):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_name": code,
						"item_group": ig,
						"stock_uom": UOM,
						"is_stock_item": 0,
						"is_sales_item": 1,
					}
				).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "t"}
			).insert(ignore_permissions=True)
		cls.cost_center = frappe.db.get_value("Cost Center", {"is_group": 0}, "name")

		# Dos Scope Items en ITEM_WA: uno CON responsable, otro SIN.
		specs = [
			("_SA_WITH", ASSIGNEE),
			("_SA_WITHOUT", None),
		]
		for i, (code, assignee) in enumerate(specs, start=1):
			if not frappe.db.exists("Scope Item", code):
				frappe.get_doc(
					{
						"doctype": "Scope Item",
						"code": code,
						"title": code,
						"sequence": i,
						"erpnext_item": ITEM_WA,
						"phase": "DISC",
						"estimated_hours": 4,
						"enabled": 1,
						"visible_in_proposal": 1,
						"default_assignee": assignee,
					}
				).insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		for pj in cls._projects:
			for t in frappe.get_all("Task", filters={"project": pj}, pluck="name"):
				for td in frappe.get_all(
					"ToDo", filters={"reference_type": "Task", "reference_name": t}, pluck="name"
				):
					try:
						frappe.delete_doc("ToDo", td, force=True, ignore_permissions=True)
					except Exception:
						pass
				try:
					frappe.delete_doc("Task", t, force=True, ignore_permissions=True)
				except Exception:
					pass
			if frappe.db.exists("Project", pj):
				try:
					frappe.delete_doc("Project", pj, force=True, ignore_permissions=True)
				except Exception:
					pass
		for name in cls._quotations:
			if frappe.db.exists("Quotation", name):
				try:
					doc = frappe.get_doc("Quotation", name)
					if doc.docstatus == 1:
						doc.flags.ignore_linked_doctypes = True
						doc.cancel()
					frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
				except Exception:
					pass
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_SA_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		cleanup_test_phases(getattr(cls, "_created_phases", None))
		cleanup_fiscal_year(getattr(cls, "_created_fy", None))
		super().tearDownClass()

	# ── Helpers ──

	def _make_quotation(self, item_codes):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "SA-" + frappe.generate_hash(length=6),
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cost_center,
				"proposal_title": "SA " + frappe.generate_hash(length=4),
				"items": [
					{"item_code": c, "item_name": c, "qty": 1, "rate": 1000, "uom": UOM} for c in item_codes
				],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._quotations.append(doc.name)
		doc.reload()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		frappe.db.set_value("Quotation", doc.name, "workflow_state", "Ganada", update_modified=False)
		return frappe.get_doc("Quotation", doc.name)

	def _assignees(self, task_name):
		raw = frappe.db.get_value("Task", task_name, "_assign") or "[]"
		try:
			return set(json.loads(raw))
		except ValueError, TypeError:
			return set()

	def _open_todos(self, task_name, user=None):
		filters = {"reference_type": "Task", "reference_name": task_name, "status": "Open"}
		if user:
			filters["allocated_to"] = user
		return frappe.get_all("ToDo", filters=filters, pluck="name")

	def _tasks(self, project):
		return frappe.get_all(
			"Task",
			filters={"project": project},
			fields=["name", "subject", "is_group", "source_quotation_scope_item"],
		)

	def _scope_code(self, row_name):
		return frappe.db.get_value("Quotation Scope Item", row_name, "code") if row_name else None

	# ── Tests ──

	def test_1_scope_with_assignee_is_assigned(self):
		q = self._make_quotation([ITEM_WA])
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])
		child_with = next(
			t
			for t in self._tasks(res["project"])
			if self._scope_code(t.source_quotation_scope_item) == "_SA_WITH"
		)
		self.assertIn(
			ASSIGNEE, self._assignees(child_with.name), "Scope con responsable → Task asignada en _assign"
		)
		self.assertTrue(
			self._open_todos(child_with.name, ASSIGNEE),
			"asignación nativa visible: existe ToDo abierto (PMO lo lee)",
		)

	def test_2_scope_without_assignee_is_unassigned(self):
		q = self._make_quotation([ITEM_WA])
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])
		child_without = next(
			t
			for t in self._tasks(res["project"])
			if self._scope_code(t.source_quotation_scope_item) == "_SA_WITHOUT"
		)
		self.assertEqual(
			self._assignees(child_without.name), set(), "Scope sin responsable → Task sin asignar"
		)
		self.assertFalse(self._open_todos(child_without.name), "sin ToDo de asignación")

	def test_3_parent_task_is_never_assigned(self):
		q = self._make_quotation([ITEM_WA])
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])
		parent = next(t for t in self._tasks(res["project"]) if t.is_group)
		self.assertEqual(self._assignees(parent.name), set(), "la Task padre nunca se asigna automáticamente")

	def test_4_operative_entregar_task_is_never_assigned(self):
		# Item vendido SIN alcance → Task operativa «Entregar» (sin Scope Item) → sin asignación.
		q = self._make_quotation([ITEM_NOSCOPE])
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])
		operative = [t for t in self._tasks(res["project"]) if not t.is_group]
		self.assertTrue(operative, "debe existir la Task operativa 'Entregar'")
		for t in operative:
			self.assertFalse(t.source_quotation_scope_item, "la operativa no proviene de un Scope Item")
			self.assertEqual(self._assignees(t.name), set(), "la Task operativa 'Entregar' no se asigna")

	def test_5_rerun_does_not_duplicate_assignment(self):
		q = self._make_quotation([ITEM_WA])
		res1 = create_project_from_quotation(q.name)
		self.__class__._projects.append(res1["project"])
		child_with = next(
			t
			for t in self._tasks(res1["project"])
			if self._scope_code(t.source_quotation_scope_item) == "_SA_WITH"
		)
		todos_before = len(self._open_todos(child_with.name, ASSIGNEE))
		assignees_before = self._assignees(child_with.name)
		# Reintento idempotente.
		create_project_from_quotation(q.name)
		self.assertEqual(len(self._open_todos(child_with.name, ASSIGNEE)), todos_before, "no duplica ToDos")
		self.assertEqual(
			self._assignees(child_with.name), assignees_before, "asignación preservada, sin duplicar"
		)


if __name__ == "__main__":
	unittest.main()
