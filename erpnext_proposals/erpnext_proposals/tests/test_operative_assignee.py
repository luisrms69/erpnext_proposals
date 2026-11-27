# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — asignación configurable de la Task operativa «Entregar» por Item Group
(`Proposal Settings.operative_assignee_rules`).

Cubre: producto de un Item Group con regla → su «Entregar» se asigna al responsable (ToDo + `_assign`);
producto de un grupo SIN regla → «Entregar» sin asignar (comportamiento por defecto); tareas padre sin
asignar; las tareas de Scope Item conservan su propio `default_assignee` (independiente de la regla
operativa); reintento sin duplicar. Genérico: no hardcodea usuarios ni grupos.
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

TEMPLATE = "_Test OA Template"
GROUP_A = "_OA Group A"  # grupo CON regla (dedicado; NO usar get_test_item_group para evitar colisión)
GROUP_B = "_OA Group B"  # grupo SIN regla
ITEM_A = "_Test OA Item A"  # grupo con regla → operativa asignada
ITEM_B = "_Test OA Item B"  # grupo SIN regla → operativa sin asignar
ITEM_C = "_Test OA Item C"  # grupo con regla pero CON scope → prueba independencia scope
OP_USER = "_oa_operative@example.com"
SCOPE_USER = "_oa_scope@example.com"
UOM = "_Test UOM"


class TestOperativeAssignee(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._quotations = []
		cls._projects = []
		cls._created_settings = False
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_company

		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company found on test site.")
		cls._created_phases = ensure_test_phases()
		cls._created_fy = ensure_current_fiscal_year()
		cls.group_a = GROUP_A  # grupo CON regla (dedicado y distinto de GROUP_B)
		cls._setup()

	@classmethod
	def _setup(cls):
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		if not cg:
			raise unittest.SkipTest("No Customer Group found.")
		terr = frappe.db.get_value("Territory", {}, "name")
		if not frappe.db.exists("Customer", "_Test OA Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test OA Customer",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test OA Customer"
		for u in (OP_USER, SCOPE_USER):
			if not frappe.db.exists("User", u):
				frappe.get_doc(
					{"doctype": "User", "email": u, "first_name": u, "send_welcome_email": 0, "enabled": 1}
				).insert(ignore_permissions=True)
		# Dos Item Groups DEDICADOS y distintos (padre robusto: el raíz de grupos). GROUP_A lleva la regla;
		# GROUP_B no. No se usa get_test_item_group para evitar que coincida con uno de estos.
		parent = frappe.db.get_value("Item Group", {"is_group": 1}, "name") or "All Item Groups"
		for grp in (GROUP_A, GROUP_B):
			if not frappe.db.exists("Item Group", grp):
				frappe.get_doc(
					{
						"doctype": "Item Group",
						"item_group_name": grp,
						"parent_item_group": parent,
						"is_group": 0,
					}
				).insert(ignore_permissions=True)
		# Items: A y C en grupo_a; B en grupo_b. A y B sin scope (→ operativa); C con scope.
		specs = [(ITEM_A, cls.group_a), (ITEM_C, cls.group_a), (ITEM_B, GROUP_B)]
		for code, grp in specs:
			if not frappe.db.exists("Item", code):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_name": code,
						"item_group": grp,
						"stock_uom": UOM,
						"is_stock_item": 0,
						"is_sales_item": 1,
					}
				).insert(ignore_permissions=True)
			else:
				frappe.db.set_value("Item", code, "item_group", grp)
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "t"}
			).insert(ignore_permissions=True)
		cls.cost_center = frappe.db.get_value("Cost Center", {"is_group": 0}, "name")
		# Scope Item SOLO para ITEM_C (con responsable propio) → prueba independencia del scope.
		if not frappe.db.exists("Scope Item", "_OA_C_SCOPE"):
			frappe.get_doc(
				{
					"doctype": "Scope Item",
					"code": "_OA_C_SCOPE",
					"title": "_OA_C_SCOPE",
					"sequence": 1,
					"erpnext_item": ITEM_C,
					"phase": "DISC",
					"estimated_hours": 2,
					"enabled": 1,
					"visible_in_proposal": 1,
					"default_assignee": SCOPE_USER,
				}
			).insert(ignore_permissions=True)
		# Proposal Settings de la Company con la regla operativa: grupo_a → OP_USER.
		name = frappe.db.get_value("Proposal Settings", {"company": cls.company}, "name")
		if name:
			ps = frappe.get_doc("Proposal Settings", name)
		else:
			ps = frappe.new_doc("Proposal Settings")
			ps.company = cls.company
			cls._created_settings = True
		ps.set("operative_assignee_rules", [])
		ps.append("operative_assignee_rules", {"item_group": cls.group_a, "assignee": OP_USER})
		ps.flags.ignore_permissions = True
		ps.save(ignore_permissions=True)

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
		# limpiar la regla operativa (o borrar el settings si lo creamos)
		psn = frappe.db.get_value("Proposal Settings", {"company": cls.company}, "name")
		if psn:
			if cls._created_settings:
				frappe.delete_doc("Proposal Settings", psn, force=True, ignore_permissions=True)
			else:
				ps = frappe.get_doc("Proposal Settings", psn)
				ps.set("operative_assignee_rules", [])
				ps.save(ignore_permissions=True)
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_OA_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		cleanup_test_phases(getattr(cls, "_created_phases", None))
		cleanup_fiscal_year(getattr(cls, "_created_fy", None))
		super().tearDownClass()

	# ── Helpers ──

	def _make_project(self, item_codes):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "OA-" + frappe.generate_hash(length=6),
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cost_center,
				"proposal_title": "OA " + frappe.generate_hash(length=4),
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
		res = create_project_from_quotation(doc.name)
		self.__class__._projects.append(res["project"])
		return res["project"]

	def _assignees(self, task_name):
		raw = frappe.db.get_value("Task", task_name, "_assign") or "[]"
		try:
			return set(json.loads(raw))
		except ValueError, TypeError:
			return set()

	def _open_todos(self, task_name):
		return frappe.get_all(
			"ToDo",
			filters={"reference_type": "Task", "reference_name": task_name, "status": "Open"},
			pluck="allocated_to",
		)

	def _tasks(self, project):
		return frappe.get_all(
			"Task",
			filters={"project": project},
			fields=[
				"name",
				"subject",
				"is_group",
				"source_quotation_scope_item",
				"source_quotation_item_row",
			],
		)

	def _operative_of(self, project, item_code):
		"""Task operativa «Entregar» (is_group=0, sin scope) cuyo Item de origen es item_code."""
		for t in self._tasks(project):
			if t.is_group or t.source_quotation_scope_item:
				continue
			qi = frappe.db.get_value("Quotation Item", t.source_quotation_item_row, "item_code")
			if qi == item_code:
				return t.name
		return None

	# ── Tests ──

	def test_1_operative_of_configured_group_is_assigned(self):
		pj = self._make_project([ITEM_A])
		op = self._operative_of(pj, ITEM_A)
		self.assertIsNotNone(op, "debe existir la operativa «Entregar» de ITEM_A")
		self.assertIn(OP_USER, self._assignees(op), "grupo con regla → operativa asignada al responsable")
		self.assertIn(OP_USER, self._open_todos(op), "asignación nativa visible (ToDo)")

	def test_2_operative_of_unconfigured_group_is_unassigned(self):
		pj = self._make_project([ITEM_B])
		op = self._operative_of(pj, ITEM_B)
		self.assertIsNotNone(op, "debe existir la operativa «Entregar» de ITEM_B")
		self.assertEqual(self._assignees(op), set(), "grupo SIN regla → operativa sin asignar")
		self.assertFalse(self._open_todos(op), "sin ToDo")

	def test_3_parent_tasks_unassigned(self):
		pj = self._make_project([ITEM_A, ITEM_B])
		for t in self._tasks(pj):
			if t.is_group:
				self.assertEqual(self._assignees(t.name), set(), "las tareas padre nunca se asignan")

	def test_4_scope_assignee_independent(self):
		# ITEM_C (grupo con regla) tiene scope → genera Task de scope (no operativa). La regla operativa NO
		# debe aplicarse a la tarea de scope; esa usa su propio default_assignee (SCOPE_USER).
		pj = self._make_project([ITEM_C])
		scope_tasks = [t for t in self._tasks(pj) if t.source_quotation_scope_item]
		self.assertTrue(scope_tasks, "ITEM_C debe generar una Task de scope")
		for t in scope_tasks:
			self.assertIn(SCOPE_USER, self._assignees(t.name), "la tarea de scope usa su propio responsable")
			self.assertNotIn(OP_USER, self._assignees(t.name), "la regla operativa no contamina el scope")
		# ITEM_C no genera operativa «Entregar» (tiene scope)
		self.assertIsNone(self._operative_of(pj, ITEM_C), "con scope no hay operativa «Entregar»")

	def test_5_rerun_does_not_duplicate(self):
		pj = self._make_project([ITEM_A])
		op = self._operative_of(pj, ITEM_A)
		before = len(self._open_todos(op))
		# reintento idempotente de materialización
		create_project_from_quotation(frappe.db.get_value("Task", op, "source_quotation"))
		self.assertEqual(len(self._open_todos(op)), before, "no duplica ToDos en reintento")


if __name__ == "__main__":
	unittest.main()
