# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tema 1 — identidad de Scope Items por FILA ORIGEN (ocurrencia comercial).

Un Scope Item de catálogo se MATERIALIZA por cada fila origen (Quotation Item / Required Item), no por
item_code. Dos filas del mismo Item producen materializaciones independientes; `qty` no multiplica. Las
Tasks siguen siendo 1 por Quotation Scope Item, y las dependencias se resuelven dentro de la misma
ocurrencia. Datos ficticios `_T1SR-*`."""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.company import get_test_company, get_test_item_group
from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils.project import create_project_from_quotation
from erpnext_proposals.erpnext_proposals.utils.quotation import (
	add_missing_scope_items_from_items,
	resync_scope_from_catalog,
)

TEMPLATE = "_T1SR Template"
ITEM_A = "_T1SR Item A"
ITEM_B = "_T1SR Item B"
ITEM_REQ = "_T1SR Item Req"
PHASE = "_T1SR_PH"
S1, S2, SREQ = "_T1SR-S1", "_T1SR-S2", "_T1SR-SREQ"


class TestScopeItemRowIdentity(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._quotations = []
		cls._projects = []
		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company on test site — run bench migrate first.")
		cls._fy = ensure_current_fiscal_year()
		ig = get_test_item_group()
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or frappe.db.get_value(
			"Territory", {}, "name"
		)
		if not cg:
			raise unittest.SkipTest("No Customer Group on test site.")
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		if not frappe.db.exists("Customer", "_T1SR Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_T1SR Customer",
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_T1SR Customer"
		cls.cost_center = frappe.db.get_value(
			"Cost Center", {"is_group": 0, "company": cls.company}, "name"
		) or frappe.db.get_value("Cost Center", {"is_group": 0}, "name")
		# Repetir el mismo Item en varias filas requiere este ajuste nativo de ERPNext (prerequisito del caso).
		cls._orig_multi = frappe.db.get_single_value("Selling Settings", "allow_multiple_items")
		frappe.db.set_single_value("Selling Settings", "allow_multiple_items", 1)
		for code, sales in ((ITEM_A, 1), (ITEM_B, 1), (ITEM_REQ, 0)):
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
						"is_purchase_item": 0,
					}
				).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "Test"}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Phase", {"phase_code": PHASE}):
			frappe.get_doc(
				{
					"doctype": "Proposal Phase",
					"phase_code": PHASE,
					"phase_name": PHASE,
					"sequence": 10,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		# S1 compartido por A y B (child N:N). S2 solo en A y depende de S1. SREQ en el Item requerido.
		cls._scope(S1, items=[ITEM_A, ITEM_B], seq=10)
		cls._scope(S2, items=[ITEM_A], seq=20, deps=[S1])
		cls._scope(SREQ, items=[ITEM_REQ], seq=10)

	@classmethod
	def tearDownClass(cls):
		for name in cls._projects:
			if frappe.db.exists("Project", name):
				for tk in frappe.get_all("Task", filters={"project": name}, pluck="name"):
					frappe.delete_doc("Task", tk, force=True, ignore_permissions=True)
				frappe.delete_doc("Project", name, force=True, ignore_permissions=True)
		for name in cls._quotations:
			if frappe.db.exists("Quotation", name):
				qd = frappe.get_doc("Quotation", name)
				if qd.docstatus == 1:
					qd.flags.ignore_permissions = True
					try:
						qd.cancel()
					except Exception:
						pass
				frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_T1SR-%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		frappe.db.set_single_value("Selling Settings", "allow_multiple_items", getattr(cls, "_orig_multi", 0))
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		frappe.db.commit()  # nosemgrep — limpieza de fixtures de test
		super().tearDownClass()

	@classmethod
	def _scope(cls, code, items, seq, deps=None):
		if frappe.db.exists("Scope Item", code):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		doc = frappe.get_doc(
			{
				"doctype": "Scope Item",
				"code": code,
				"title": code,
				"sequence": seq,
				"enabled": 1,
				"visible_in_proposal": 1,
				"phase": PHASE,
				"estimated_hours": 4,
			}
		)
		for it in items:
			doc.append("erpnext_items", {"item": it})
		for d in deps or []:
			doc.append("depends_on_scope_items", {"depends_on": d})
		doc.insert(ignore_permissions=True)

	def _make(self, sold_rows, required_rows=None, ganada=False):
		"""sold_rows / required_rows: listas de item_codes; un código repetido = filas repetidas."""
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "T1SR-" + frappe.generate_hash(length=8),
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cost_center,
				"proposal_title": "T1SR " + frappe.generate_hash(length=4),
				"items": [
					{"item_code": c, "item_name": c, "qty": 1, "rate": 1000, "uom": "Nos"} for c in sold_rows
				],
				"required_items": [{"item": c, "qty": 1, "uom": "Nos"} for c in (required_rows or [])],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._quotations.append(doc.name)
		if ganada:
			doc.reload()
			doc.flags.ignore_mandatory = True
			doc.flags.ignore_links = True
			doc.submit()
			frappe.db.set_value("Quotation", doc.name, "workflow_state", "Ganada", update_modified=False)
		return frappe.get_doc("Quotation", doc.name)

	@staticmethod
	def _rows(name):
		return frappe.get_doc("Quotation", name).quotation_scope_items

	def _count(self, name, scope):
		return sum(1 for r in self._rows(name) if r.scope_item == scope)

	def _keys(self, name, scope):
		return {(r.source_type, r.source_row) for r in self._rows(name) if r.scope_item == scope}

	# ── Casos obligatorios A-E ─────────────────────────────────────────────
	def test_A_shared_scope_two_items(self):
		# S1 pertenece a A y B; Quotation [A, B] → 2 materializaciones (una por Item).
		q = self._make([ITEM_A, ITEM_B])
		self.assertEqual(self._count(q.name, S1), 2)
		self.assertEqual(len(self._keys(q.name, S1)), 2)  # dos filas origen distintas

	def test_B_same_item_two_rows(self):
		# Mismo Item A en dos filas → 2 materializaciones de S1 (distinta source_row).
		q = self._make([ITEM_A, ITEM_A])
		self.assertEqual(self._count(q.name, S1), 2)
		rows = [r for r in self._rows(q.name) if r.scope_item == S1]
		self.assertEqual(len({r.source_row for r in rows}), 2)  # source_row distinto por ocurrencia
		self.assertTrue(all(r.source_type == "sold" for r in rows))

	def test_C_qty_does_not_multiply(self):
		# Una sola fila A con qty=5 → 1 materialización de S1 (qty NO multiplica).
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "T1SR-" + frappe.generate_hash(length=8),
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cost_center,
				"items": [{"item_code": ITEM_A, "item_name": ITEM_A, "qty": 5, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._quotations.append(doc.name)
		self.assertEqual(self._count(doc.name, S1), 1)

	def test_D_two_scopes_repeated_item(self):
		# A tiene S1 y S2; Quotation [A, A] → 4 materializaciones (S1@A1,S2@A1,S1@A2,S2@A2).
		q = self._make([ITEM_A, ITEM_A])
		self.assertEqual(self._count(q.name, S1), 2)
		self.assertEqual(self._count(q.name, S2), 2)
		self.assertEqual(len([r for r in self._rows(q.name) if r.item_code == ITEM_A]), 4)

	def test_E_required_item_repeated(self):
		# Dos filas de Required Item con el mismo item_code → materializaciones independientes.
		q = self._make([ITEM_A], required_rows=[ITEM_REQ, ITEM_REQ])
		self.assertEqual(self._count(q.name, SREQ), 2)
		rows = [r for r in self._rows(q.name) if r.scope_item == SREQ]
		self.assertEqual(len({r.source_row for r in rows}), 2)
		self.assertTrue(all(r.source_type == "required" for r in rows))

	# ── Generator / add-missing / delete / resync por fila origen ──────────
	def test_F_add_missing_respects_source_row(self):
		# Borrar S1 de la ocurrencia A1; add-missing lo repone SOLO para esa fila (no duplica A2).
		q = self._make([ITEM_A, ITEM_A])
		doc = frappe.get_doc("Quotation", q.name)
		s1_rows = [r for r in doc.quotation_scope_items if r.scope_item == S1]
		drop = s1_rows[0].source_row
		doc.set(
			"quotation_scope_items",
			[r for r in doc.quotation_scope_items if not (r.scope_item == S1 and r.source_row == drop)],
		)
		doc.save(ignore_permissions=True)
		self.assertEqual(self._count(q.name, S1), 1)  # quedó 1
		res = add_missing_scope_items_from_items(q.name)
		self.assertEqual(res["added"], 1)  # repone solo la ocurrencia faltante
		self.assertEqual(self._count(q.name, S1), 2)
		self.assertEqual(add_missing_scope_items_from_items(q.name)["added"], 0)  # idempotente

	def test_G_delete_then_save_no_reappear(self):
		q = self._make([ITEM_A, ITEM_A])
		doc = frappe.get_doc("Quotation", q.name)
		drop = next(r for r in doc.quotation_scope_items if r.scope_item == S1).source_row
		doc.set(
			"quotation_scope_items",
			[r for r in doc.quotation_scope_items if not (r.scope_item == S1 and r.source_row == drop)],
		)
		doc.save(ignore_permissions=True)
		frappe.get_doc("Quotation", q.name).save(ignore_permissions=True)  # guardar de nuevo
		self.assertEqual(self._count(q.name, S1), 1)  # no reaparece

	def test_H_resync_does_not_reinsert_deleted(self):
		q = self._make([ITEM_A, ITEM_A])
		doc = frappe.get_doc("Quotation", q.name)
		drop = next(r for r in doc.quotation_scope_items if r.scope_item == S1).source_row
		doc.set(
			"quotation_scope_items",
			[r for r in doc.quotation_scope_items if not (r.scope_item == S1 and r.source_row == drop)],
		)
		doc.save(ignore_permissions=True)
		resync_scope_from_catalog(q.name)
		self.assertEqual(self._count(q.name, S1), 1)  # resync no repone

	# ── Tasks + dependencias por ocurrencia ────────────────────────────────
	def test_I_one_qsi_row_one_task(self):
		q = self._make([ITEM_A, ITEM_A], ganada=True)
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])
		exec_rows = [r for r in self._rows(q.name) if r.include_in_proposal or r.is_internal_cost_task]
		children = frappe.get_all("Task", filters={"project": res["project"], "is_group": 0}, pluck="name")
		self.assertEqual(len(children), len(exec_rows))  # 1 QSI row → 1 Task (4 filas → 4 hijas)

	def test_J_dependencies_resolve_within_occurrence(self):
		# [A, A] con S2 depende de S1 → S1@A1→S2@A1 y S1@A2→S2@A2 (nunca cruzado).
		q = self._make([ITEM_A, ITEM_A], ganada=True)
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])
		self.assertEqual(res.get("dependencies_ambiguous", 0), 0)
		# mapear (source_row) -> task para S1 y S2
		rows = self._rows(q.name)
		s1_task = {r.source_row: r.project_task for r in rows if r.scope_item == S1}
		s2_task = {r.source_row: r.project_task for r in rows if r.scope_item == S2}
		self.assertEqual(len(s1_task), 2)
		self.assertEqual(len(s2_task), 2)
		for src_row, s2t in s2_task.items():
			deps = frappe.get_all("Task Depends On", filters={"parent": s2t}, pluck="task")
			# S2 de esta ocurrencia depende de S1 de LA MISMA ocurrencia, y solo de ella.
			self.assertEqual(deps, [s1_task[src_row]], f"ocurrencia {src_row}: deps={deps}")


if __name__ == "__main__":
	unittest.main()
