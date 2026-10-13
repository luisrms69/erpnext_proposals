# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Integración: jerarquía y fechas Quotation Ganada → Project → Task padre-Item → Task hija.

Genera el Project COMPLETO desde una Quotation y consulta las Tasks **persistidas en BD** en los dos
niveles (padre `is_group=1` + hoja `is_group=0`), verificando `exp_start_date`/`exp_end_date`. Contrato
(ADR-0025 + v0.36.1 + fix rollup):

- `Project.expected_start_date` = ancla (fecha de la Cotización); no se modifica.
- Task operativa «Entregar»: inicio = ancla del Project; sin fin (hasta que haya planificación).
- Task hija de Scope: respeta offset/duración/dependencias; sin planeación → sin fechas.
- Task padre-Item: hereda el inicio MÁS TEMPRANO de sus hijas (independiente del fin); refleja el fin
  más tardío de sus hijas SOLO cuando alguna tiene fin (no se inventa).
- Reejecución idempotente: sin duplicados ni sobrescritura de la fecha editada manualmente en una hoja.
- Addenda: preserva fechas existentes y materializa correctamente las Tasks nuevas.

Datos ficticios. Esta es la cobertura que faltaba en v0.36.1 (los tests verificaban la hoja operativa
pero NO la fecha de la Task padre en el caso sin Scope Items).
"""

import unittest

import frappe
from frappe.tests import change_settings
from frappe.utils import add_days, getdate

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
from erpnext_proposals.erpnext_proposals.utils.project import (
	apply_addendum_to_project,
	create_project_from_quotation,
)

TEMPLATE = "_PDH Template"
PHASE = "_PDH_PHASE"

IT_SIMPLE = "_PDH Simple"  # vendido sin scope → Task operativa
IT_SIMPLE2 = "_PDH Simple2"  # segundo vendido sin scope
IT_SCOPED = "_PDH Scoped"  # vendido con scope PROGRAMADO (offset/duración)
IT_SCOPED_NP = "_PDH ScopedNP"  # vendido con scope SIN programación

SC = "_PDH_SC"  # scope programado de IT_SCOPED (offset "0", dur 3)
SNP = "_PDH_SNP"  # scope sin programación de IT_SCOPED_NP
DUR = 3


class TestProjectDateHierarchy(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._q = []
		cls._p = []
		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company on test site.")
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
		if not frappe.db.exists("Customer", "_PDH Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_PDH Customer",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_PDH Customer"
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
		for code in (IT_SIMPLE, IT_SIMPLE2, IT_SCOPED, IT_SCOPED_NP):
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
						"is_purchase_item": 0,
					}
				).insert(ignore_permissions=True)
		cls._scope(SC, IT_SCOPED, offset="0", duration=DUR)  # programado
		cls._scope(SNP, IT_SCOPED_NP, offset=None, duration=None)  # sin programación
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
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_PDH_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		frappe.db.commit()  # nosemgrep — limpieza de fixtures de test
		super().tearDownClass()

	# ── helpers ─────────────────────────────────────────────────────────────
	@classmethod
	def _scope(cls, code, item, offset, duration):
		if frappe.db.exists("Scope Item", code):
			return
		frappe.get_doc(
			{
				"doctype": "Scope Item",
				"code": code,
				"title": code,
				"sequence": 10,
				"enabled": 1,
				"visible_in_proposal": 1,
				"estimated_hours": 4,
				"phase": PHASE,
				"erpnext_item": item,
				"planned_start_offset_days": offset,
				"planned_duration_days": duration,
			}
		).insert(ignore_permissions=True)

	def _quotation(self, item_codes, group=None, addendum=False):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": group or ("PDH-" + frappe.generate_hash(length=8)),
				"company": self.company,
				"currency": "MXN",
				"selling_price_list": self.price_list,
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cc,
				"proposal_title": "PDH " + frappe.generate_hash(length=4),
				"items": [
					{"item_code": c, "item_name": c, "qty": 1, "rate": 1000, "uom": "Nos"} for c in item_codes
				],
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
		res = create_project_from_quotation(doc.name)
		self.__class__._p.append(res["project"])
		return res["project"]

	def _parents(self, project):
		return frappe.get_all(
			"Task",
			filters={"project": project, "is_group": 1},
			fields=["name", "subject", "exp_start_date", "exp_end_date", "source_quotation_item_row"],
		)

	def _leaves(self, project):
		return frappe.get_all(
			"Task",
			filters={"project": project, "is_group": 0},
			fields=[
				"name",
				"subject",
				"parent_task",
				"exp_start_date",
				"exp_end_date",
				"source_quotation_scope_item",
			],
		)

	def _anchor(self, project):
		return getdate(frappe.db.get_value("Project", project, "expected_start_date"))

	# ── casos ────────────────────────────────────────────────────────────────
	def test_01_single_item_no_scope_full_hierarchy(self):
		q = self._quotation([IT_SIMPLE])
		proj = self._win(q)
		anchor = self._anchor(proj)
		self.assertEqual(anchor, getdate(frappe.utils.today()), "ancla del Project = fecha de la Cotización")
		parents = self._parents(proj)
		leaves = self._leaves(proj)
		self.assertEqual(len(parents), 1, "un padre-Item")
		self.assertEqual(len(leaves), 1, "una hija operativa")
		op = leaves[0]
		self.assertTrue(op.subject.startswith("Entregar — "))
		self.assertEqual(getdate(op.exp_start_date), anchor, "operativa inicia en el ancla")
		self.assertIsNone(op.exp_end_date, "operativa sin fin")
		par = parents[0]
		self.assertEqual(getdate(par.exp_start_date), anchor, "PADRE hereda el inicio de la operativa")
		self.assertIsNone(par.exp_end_date, "PADRE sin fin (ninguna hija tiene fin)")
		self.assertEqual(op.parent_task, par.name, "la operativa cuelga del padre-Item")

	def test_02_multiple_items_no_scope(self):
		q = self._quotation([IT_SIMPLE, IT_SIMPLE2])
		proj = self._win(q)
		anchor = self._anchor(proj)
		parents = self._parents(proj)
		leaves = self._leaves(proj)
		self.assertEqual(len(parents), 2, "dos padres-Item")
		self.assertEqual(len(leaves), 2, "dos operativas")
		for par in parents:
			self.assertEqual(getdate(par.exp_start_date), anchor, f"padre {par.subject} inicia en ancla")
			self.assertIsNone(par.exp_end_date, "padre sin fin")
		# cada operativa cuelga de un padre distinto
		self.assertEqual({op.parent_task for op in leaves}, {p.name for p in parents})
		for op in leaves:
			self.assertEqual(getdate(op.exp_start_date), anchor)
			self.assertIsNone(op.exp_end_date)

	def test_03_item_with_programmed_scope_rollup(self):
		q = self._quotation([IT_SCOPED])
		proj = self._win(q)
		anchor = self._anchor(proj)
		parents = self._parents(proj)
		leaves = self._leaves(proj)
		self.assertEqual(len(parents), 1)
		self.assertEqual(len(leaves), 1, "una hija de scope (no operativa)")
		sc = leaves[0]
		self.assertTrue(sc.source_quotation_scope_item, "es Task de Scope, no operativa")
		self.assertEqual(getdate(sc.exp_start_date), anchor, "scope offset '0' → inicio en ancla")
		self.assertEqual(getdate(sc.exp_end_date), add_days(anchor, DUR - 1), "fin = inicio + dur - 1")
		par = parents[0]
		self.assertEqual(getdate(par.exp_start_date), anchor, "padre = inicio de la hija")
		self.assertEqual(getdate(par.exp_end_date), add_days(anchor, DUR - 1), "padre = fin de la hija")

	def test_04_item_with_unscheduled_scope_no_dates(self):
		q = self._quotation([IT_SCOPED_NP])
		proj = self._win(q)
		leaves = self._leaves(proj)
		parents = self._parents(proj)
		self.assertEqual(len(leaves), 1)
		sc = leaves[0]
		self.assertTrue(sc.source_quotation_scope_item, "hija de scope")
		self.assertIsNone(sc.exp_start_date, "scope sin offset ni dependencia → sin inicio (no se inventa)")
		self.assertIsNone(sc.exp_end_date, "sin fin")
		self.assertIsNone(parents[0].exp_start_date, "padre sin hijas fechadas → sin inicio")
		self.assertIsNone(parents[0].exp_end_date, "padre sin fin")

	def test_05_mixed_scoped_and_simple(self):
		q = self._quotation([IT_SCOPED, IT_SIMPLE])
		proj = self._win(q)
		anchor = self._anchor(proj)
		parents = {p.subject: p for p in self._parents(proj)}
		self.assertEqual(len(parents), 2, "un padre por Item")
		scoped = next(p for s, p in parents.items() if IT_SCOPED in s)
		simple = next(p for s, p in parents.items() if IT_SIMPLE in s and IT_SCOPED not in s)
		# scoped: fechado por la hija de scope
		self.assertEqual(getdate(scoped.exp_start_date), anchor)
		self.assertEqual(getdate(scoped.exp_end_date), add_days(anchor, DUR - 1))
		# simple: inicio por la operativa, sin fin
		self.assertEqual(getdate(simple.exp_start_date), anchor)
		self.assertIsNone(simple.exp_end_date)

	def test_06_idempotent_preserves_manual_leaf_date(self):
		q = self._quotation([IT_SIMPLE])
		proj = self._win(q)
		op = self._leaves(proj)[0]
		n_parents = len(self._parents(proj))
		n_leaves = len(self._leaves(proj))
		# El usuario edita manualmente la fecha de inicio de la hoja operativa.
		edited = add_days(getdate(frappe.utils.today()), 5)
		frappe.db.set_value("Task", op.name, "exp_start_date", edited, update_modified=False)
		# Reejecutar la generación (idempotente).
		create_project_from_quotation(q.name)
		leaves2 = self._leaves(proj)
		parents2 = self._parents(proj)
		self.assertEqual(len(parents2), n_parents, "sin padres duplicados")
		self.assertEqual(len(leaves2), n_leaves, "sin operativas duplicadas")
		op2 = next(x for x in leaves2 if x.name == op.name)
		self.assertEqual(
			getdate(op2.exp_start_date), edited, "NO se sobrescribe la fecha editada manualmente"
		)
		# El padre refleja el inicio real de su hija (la edición), sin inventar fin.
		self.assertEqual(
			getdate(parents2[0].exp_start_date), edited, "padre refleja el inicio real de la hija"
		)
		self.assertIsNone(parents2[0].exp_end_date)

	def test_07_addendum_new_item_dated_preserves_existing(self):
		# Root con Item scope programado → Project con padre fechado.
		root = self._quotation([IT_SCOPED])
		proj = self._win(root)
		anchor = self._anchor(proj)
		before = {
			t.name: (t.exp_start_date, t.exp_end_date) for t in self._parents(proj) + self._leaves(proj)
		}
		# Addenda canónica ROOT-ADD-01 con un Item vendido SIN scope → nuevo padre + operativa.
		add = self._quotation([IT_SIMPLE], group=f"{root.proposal_group}-ADD-01", addendum=True)
		add.reload()
		add.flags.ignore_mandatory = True
		add.flags.ignore_links = True
		add.submit()
		frappe.db.set_value("Quotation", add.name, "workflow_state", "Ganada", update_modified=False)
		apply_addendum_to_project(add.name, proj)
		# Fechas previas intactas.
		for t in self._parents(proj) + self._leaves(proj):
			if t.name in before:
				self.assertEqual(
					(t.exp_start_date, t.exp_end_date), before[t.name], f"fecha previa intacta: {t.subject}"
				)
		# Nueva jerarquía del Item de la addenda: padre con inicio = ancla, operativa con inicio = ancla.
		new_op = next(
			t for t in self._leaves(proj) if t.subject.startswith("Entregar — ") and IT_SIMPLE in t.subject
		)
		self.assertEqual(getdate(new_op.exp_start_date), anchor, "operativa de la addenda inicia en el ancla")
		self.assertIsNone(new_op.exp_end_date)
		new_par = next(t for t in self._parents(proj) if t.name == new_op.parent_task)
		self.assertEqual(
			getdate(new_par.exp_start_date), anchor, "padre nuevo hereda el inicio de su operativa"
		)
		self.assertIsNone(new_par.exp_end_date)

	def test_08_three_same_item_no_scope(self):
		# Tres ocurrencias del MISMO Item vendido sin scope → 3 padres + 3 operativas, todas fechadas.
		with change_settings("Selling Settings", {"allow_multiple_items": 1}):
			q = self._quotation([IT_SIMPLE, IT_SIMPLE, IT_SIMPLE])
			proj = self._win(q)
		anchor = self._anchor(proj)
		parents = self._parents(proj)
		leaves = self._leaves(proj)
		self.assertEqual(len(parents), 3, "un padre por ocurrencia")
		self.assertEqual(len(leaves), 3, "una operativa por ocurrencia")
		for par in parents:
			self.assertEqual(getdate(par.exp_start_date), anchor)
			self.assertIsNone(par.exp_end_date)
		self.assertEqual({op.parent_task for op in leaves}, {p.name for p in parents}, "1:1 padre↔operativa")
