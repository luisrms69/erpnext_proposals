"""TASK 2 — Tests de integración Project/Task, tarea interna de costo e inmutabilidad.

Cubre: jerarquía Phase→Task padre / Scope→Task hija, filtro include OR internal en costo/Tasks,
exclusión total (0/0), validación 1/1, bloqueo por fase faltante, idempotencia, visibilidad en PDF,
y que una propuesta congelada no se altera por save/resync/cambio de catálogo.
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
from erpnext_proposals.erpnext_proposals.utils.project import create_project_from_quotation
from erpnext_proposals.erpnext_proposals.utils.quotation import resync_scope_from_catalog

TEMPLATE = "_Test PTI Template"
ITEM_A = "_Test PTI Item A"
ITEM_B = "_Test PTI Item B"


class TestProjectTaskIntegration(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._quotations = []
		cls._projects = []
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_company

		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company found on test site.")
		cls._created_phases = ensure_test_phases()  # DISC(10), IMPL(20), GOLIVE(30)
		cls._created_fy = ensure_current_fiscal_year()
		cls._setup()

	@classmethod
	def tearDownClass(cls):
		for pj in cls._projects:
			for t in frappe.get_all("Task", filters={"project": pj}, pluck="name"):
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
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_PTI_%"]}, pluck="name"):
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
		if not frappe.db.exists("Customer", "_Test PTI Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test PTI Customer",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test PTI Customer"
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		ig = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		for code in (ITEM_A, ITEM_B):
			if not frappe.db.exists("Item", code):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_name": code,
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

		# Scope Items en ITEM_A:
		#  (code, phase, visible_in_proposal, is_internal_cost_task)
		specs = [
			("_PTI_A1", "DISC", 1, 0),  # vendible
			("_PTI_A2", "DISC", 1, 0),  # vendible (misma fase)
			("_PTI_A3", "IMPL", 1, 0),  # vendible
			("_PTI_INT", "IMPL", 0, 1),  # interna de costo
			("_PTI_EXCL", "GOLIVE", 0, 0),  # excluida total
		]
		for i, (code, phase, vis, internal) in enumerate(specs, start=1):
			if not frappe.db.exists("Scope Item", code):
				frappe.get_doc(
					{
						"doctype": "Scope Item",
						"code": code,
						"title": code,
						"sequence": i,
						"erpnext_item": ITEM_A,
						"phase": phase,
						"estimated_hours": 5,
						"enabled": 1,
						"visible_in_proposal": vis,
						"is_internal_cost_task": internal,
					}
				).insert(ignore_permissions=True)
		# Scope Item SIN fase en ITEM_B (para el test de bloqueo).
		if not frappe.db.exists("Scope Item", "_PTI_B_NOPHASE"):
			frappe.get_doc(
				{
					"doctype": "Scope Item",
					"code": "_PTI_B_NOPHASE",
					"title": "_PTI_B_NOPHASE",
					"sequence": 1,
					"erpnext_item": ITEM_B,
					"estimated_hours": 3,
					"enabled": 1,
					"visible_in_proposal": 1,
				}
			).insert(ignore_permissions=True)

	# ── Helpers ──

	def _make_quotation(self, item_codes, submit=False, ganada=False):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "PTI-" + frappe.generate_hash(length=6),
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cost_center,
				"proposal_title": "PTI " + frappe.generate_hash(length=4),
				"items": [
					{"item_code": c, "item_name": c, "qty": 1, "rate": 1000, "uom": "Nos"} for c in item_codes
				],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._quotations.append(doc.name)
		if submit or ganada:
			doc.reload()
			doc.flags.ignore_mandatory = True
			doc.flags.ignore_links = True
			doc.submit()
		if ganada:
			frappe.db.set_value("Quotation", doc.name, "workflow_state", "Ganada", update_modified=False)
		return frappe.get_doc("Quotation", doc.name)

	# ── Jerarquía / Project ──

	def test_hierarchy_and_flags(self):
		q = self._make_quotation([ITEM_A], ganada=True)
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])

		tasks = frappe.get_all(
			"Task",
			filters={"project": res["project"]},
			fields=[
				"name",
				"subject",
				"is_group",
				"parent_task",
				"proposal_phase",
				"source_quotation_scope_item",
			],
		)
		parents = [t for t in tasks if t.is_group]
		children = [t for t in tasks if not t.is_group]

		# 2 fases con filas ejecutables (DISC, IMPL) → 2 padres; GOLIVE solo tenía la excluida.
		self.assertEqual(len(parents), 2, f"Esperados 2 Task padre por fase; tasks={tasks}")
		self.assertEqual({p.proposal_phase for p in parents}, {"DISC", "IMPL"})
		for p in parents:
			self.assertTrue(p.is_group)
			self.assertTrue(p.proposal_phase)

		# 4 hijas: A1,A2 (DISC) + A3, INT (IMPL). EXCL (0/0) NO genera Task.
		self.assertEqual(len(children), 4, f"Esperadas 4 Task hijas; children={children}")
		for c in children:
			self.assertTrue(c.parent_task, "Task hija debe tener parent_task (fase)")
			self.assertTrue(c.source_quotation_scope_item, "Task hija debe trazar la fila de scope")
		# La interna genera Task; la excluida no.
		scope_codes = {
			frappe.db.get_value("Quotation Scope Item", c.source_quotation_scope_item, "code")
			for c in children
		}
		self.assertIn("_PTI_INT", scope_codes)
		self.assertNotIn("_PTI_EXCL", scope_codes)

	def test_idempotent_project_creation(self):
		q = self._make_quotation([ITEM_A], ganada=True)
		res1 = create_project_from_quotation(q.name)
		self.__class__._projects.append(res1["project"])
		n1 = frappe.db.count("Task", {"project": res1["project"]})
		res2 = create_project_from_quotation(q.name)
		n2 = frappe.db.count("Task", {"project": res2["project"]})
		self.assertEqual(res1["project"], res2["project"])
		self.assertEqual(n1, n2, "No debe duplicar Tasks al re-crear")
		self.assertEqual(res2["tasks_created"], 0)

	def test_block_when_executable_row_without_phase(self):
		q = self._make_quotation([ITEM_B], ganada=True)  # _PTI_B_NOPHASE ejecutable sin fase
		with self.assertRaises(ValidationError):
			create_project_from_quotation(q.name)

	# ── Costeo / visibilidad ──

	def test_internal_in_cost_not_in_pdf(self):
		q = self._make_quotation([ITEM_A], submit=True)
		# Costeo incluye la interna, excluye la excluida.
		data = get_profitability_data(q.name)
		labor_codes = {r.get("title") for r in data["labor_rows"]}
		self.assertIn("_PTI_INT", labor_codes, "La interna debe entrar al costeo")
		self.assertNotIn("_PTI_EXCL", labor_codes, "La excluida NO entra al costeo")
		# PDF cliente: NO muestra la interna ni la excluida; sí las vendibles.
		html = frappe.get_print("Quotation", q.name, print_format="Propuesta Comercial")
		self.assertIn("_PTI_A1", html)
		self.assertNotIn("_PTI_INT", html)
		self.assertNotIn("_PTI_EXCL", html)

	# ── Validación 1/1 ──

	def test_invalid_flag_combination_rejected(self):
		q = self._make_quotation([ITEM_A])
		row = next(r for r in q.quotation_scope_items if r.code == "_PTI_A1")
		row.include_in_proposal = 1
		row.is_internal_cost_task = 1
		with self.assertRaises(ValidationError):
			q.save(ignore_permissions=True)

	# ── Inmutabilidad ──

	def test_frozen_rejects_flag_change(self):
		q = self._make_quotation([ITEM_A], submit=True)  # congelada (docstatus=1)
		fresh = frappe.get_doc("Quotation", q.name)
		row = next(r for r in fresh.quotation_scope_items if r.code == "_PTI_A2")
		original = row.is_internal_cost_task
		row.is_internal_cost_task = 1 if not original else 0
		with self.assertRaises(ValidationError):
			fresh.save(ignore_permissions=True)
		again = frappe.get_doc("Quotation", q.name)
		r2 = next(r for r in again.quotation_scope_items if r.code == "_PTI_A2")
		self.assertEqual(r2.is_internal_cost_task, original, "La fase congelada no debe cambiar")

	def test_frozen_rejects_resync(self):
		q = self._make_quotation([ITEM_A], submit=True)
		with self.assertRaises(ValidationError):
			resync_scope_from_catalog(q.name)

	def test_catalog_change_does_not_affect_frozen(self):
		q = self._make_quotation([ITEM_A], submit=True)
		before = {
			r.code: r.is_internal_cost_task for r in frappe.get_doc("Quotation", q.name).quotation_scope_items
		}
		# Cambiar el catálogo (marcar A1 como interna).
		si = frappe.get_doc("Scope Item", "_PTI_A1")
		orig = si.is_internal_cost_task
		si.is_internal_cost_task = 1
		si.visible_in_proposal = 0
		si.save(ignore_permissions=True)
		try:
			after = {
				r.code: r.is_internal_cost_task
				for r in frappe.get_doc("Quotation", q.name).quotation_scope_items
			}
			self.assertEqual(before, after, "El cambio de catálogo no debe tocar la propuesta congelada")
		finally:
			si.is_internal_cost_task = orig
			si.visible_in_proposal = 1
			si.save(ignore_permissions=True)
