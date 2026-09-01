# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Autopoblado de alcance en Quotation con la nueva relación N:N + resolver central.

Reglas verificadas:
- captura inicial genera para todos los Items (legacy o child);
- guardar NO repuebla (una fila borrada no reaparece; editar no agrega);
- agregar un Item nuevo genera solo el alcance de ese Item;
- acción manual `add_missing_scope_items_from_items` recupera faltantes (idempotente);
- resync actualiza existentes pero NO agrega faltantes.
Datos ficticios."""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.company import get_test_company, get_test_item_group
from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils.quotation import (
	add_missing_scope_items_from_items,
	resync_scope_from_catalog,
)

TEMPLATE = "_Test Gen Template"
ITEM_G1 = "_Test Gen Item G1"  # scope por legacy erpnext_item
ITEM_G2 = "_Test Gen Item G2"  # scope por child erpnext_items


class TestScopeItemGeneration(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._quotations = []
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
		if not frappe.db.exists("Customer", "_Test Gen Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test Gen Customer",
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test Gen Customer"
		cls.cost_center = frappe.db.get_value(
			"Cost Center", {"is_group": 0, "company": cls.company}, "name"
		) or frappe.db.get_value("Cost Center", {"is_group": 0}, "name")
		for code in (ITEM_G1, ITEM_G2):
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
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "Test"}
			).insert(ignore_permissions=True)
		# Scope Items: G1 por legacy (2), G2 por child (1).
		cls._make_scope("_SG1A", ITEM_G1, legacy=True, seq=10)
		cls._make_scope("_SG1B", ITEM_G1, legacy=True, seq=20)
		cls._make_scope("_SG2A", ITEM_G2, legacy=False, seq=10)

	@classmethod
	def tearDownClass(cls):
		for name in cls._quotations:
			if frappe.db.exists("Quotation", name):
				frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_SG%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		frappe.db.commit()  # nosemgrep — limpieza de fixtures de test
		super().tearDownClass()

	@classmethod
	def _make_scope(cls, code, item, legacy, seq):
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
				"erpnext_item": item if legacy else None,
			}
		)
		if not legacy:
			doc.append("erpnext_items", {"item": item})
		doc.insert(ignore_permissions=True)

	def _make_quotation(self, item_codes):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "GEN-" + frappe.generate_hash(length=8),
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"workflow_state": "Borrador",
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cost_center,
				"items": [
					{"item_code": c, "item_name": c, "qty": 1, "rate": 1000, "uom": "Nos"} for c in item_codes
				],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._quotations.append(doc.name)
		return doc

	@staticmethod
	def _scopes(name):
		return {r.scope_item for r in frappe.get_doc("Quotation", name).quotation_scope_items}

	# 7. captura inicial autopuebla (legacy).
	def test_initial_autopopulate(self):
		q = self._make_quotation([ITEM_G1])
		self.assertEqual(self._scopes(q.name), {"_SG1A", "_SG1B"})

	# child path también genera.
	def test_initial_autopopulate_child(self):
		q = self._make_quotation([ITEM_G2])
		self.assertEqual(self._scopes(q.name), {"_SG2A"})

	# 8. borrar Scope Item + guardar → NO reaparece.
	def test_delete_then_save_no_reappear(self):
		q = self._make_quotation([ITEM_G1])
		doc = frappe.get_doc("Quotation", q.name)
		doc.set("quotation_scope_items", [r for r in doc.quotation_scope_items if r.scope_item != "_SG1A"])
		doc.save(ignore_permissions=True)
		self.assertEqual(self._scopes(q.name), {"_SG1B"})  # _SG1A NO reaparece
		# guardar otra vez tampoco lo repone
		frappe.get_doc("Quotation", q.name).save(ignore_permissions=True)
		self.assertEqual(self._scopes(q.name), {"_SG1B"})

	# 9. editar + guardar → no agrega faltantes.
	def test_edit_then_save_no_add(self):
		q = self._make_quotation([ITEM_G1])
		doc = frappe.get_doc("Quotation", q.name)
		doc.set("quotation_scope_items", [r for r in doc.quotation_scope_items if r.scope_item != "_SG1A"])
		doc.save(ignore_permissions=True)
		doc = frappe.get_doc("Quotation", q.name)
		doc.items[0].rate = 2500  # editar precio
		doc.save(ignore_permissions=True)
		self.assertEqual(self._scopes(q.name), {"_SG1B"})  # sigue sin _SG1A

	# 10. agregar Item nuevo → agrega solo el alcance de ese Item.
	def test_add_new_item_generates_only_its_scope(self):
		q = self._make_quotation([ITEM_G1])
		doc = frappe.get_doc("Quotation", q.name)
		doc.append(
			"items", {"item_code": ITEM_G2, "item_name": ITEM_G2, "qty": 1, "rate": 1000, "uom": "Nos"}
		)
		doc.save(ignore_permissions=True)
		self.assertEqual(self._scopes(q.name), {"_SG1A", "_SG1B", "_SG2A"})

	# 11 + 12. acción manual recupera faltantes; segunda ejecución no duplica.
	def test_manual_add_missing(self):
		q = self._make_quotation([ITEM_G1])
		doc = frappe.get_doc("Quotation", q.name)
		doc.set("quotation_scope_items", [r for r in doc.quotation_scope_items if r.scope_item != "_SG1A"])
		doc.save(ignore_permissions=True)
		res = add_missing_scope_items_from_items(q.name)
		self.assertEqual(res["added"], 1)
		self.assertEqual(self._scopes(q.name), {"_SG1A", "_SG1B"})
		res2 = add_missing_scope_items_from_items(q.name)
		self.assertEqual(res2["added"], 0)  # idempotente

	# 13. resync actualiza existentes.
	def test_resync_updates_existing(self):
		q = self._make_quotation([ITEM_G1])
		frappe.db.set_value("Scope Item", "_SG1A", "title", "TITULO NUEVO")
		resync_scope_from_catalog(q.name)
		row = next(
			r for r in frappe.get_doc("Quotation", q.name).quotation_scope_items if r.scope_item == "_SG1A"
		)
		self.assertEqual(row.title, "TITULO NUEVO")

	# 14. resync NO agrega eliminados/faltantes.
	def test_resync_does_not_add(self):
		q = self._make_quotation([ITEM_G1])
		doc = frappe.get_doc("Quotation", q.name)
		doc.set("quotation_scope_items", [r for r in doc.quotation_scope_items if r.scope_item != "_SG1B"])
		doc.save(ignore_permissions=True)
		res = resync_scope_from_catalog(q.name)
		self.assertNotIn("added", res)
		self.assertEqual(self._scopes(q.name), {"_SG1A"})  # _SG1B NO reaparece


if __name__ == "__main__":
	unittest.main()
