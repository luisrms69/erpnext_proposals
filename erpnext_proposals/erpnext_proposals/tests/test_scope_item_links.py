# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Relación N:N Scope Item ↔ ERPNext Item: resolver central (child + legacy) + edición desde Item.

Sin migración masiva: la compatibilidad legacy es por LECTURA (`resolve_scope_items_for_item`).
No ejercita generación de alcance en Quotation (ver test_scope_item_generation). Datos ficticios."""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.company import get_test_item_group
from erpnext_proposals.erpnext_proposals.utils import scope_item_links as links


def _item(code: str) -> str:
	grp = get_test_item_group()
	uom = "Nos" if frappe.db.exists("UOM", "Nos") else frappe.db.get_value("UOM", {}, "name")
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": grp,
				"stock_uom": uom,
				"is_stock_item": 0,
				"is_sales_item": 1,
			}
		).insert(ignore_permissions=True)
	return code


def _scope(code, enabled=1, erpnext_item=None, items=None):
	if frappe.db.exists("Scope Item", code):
		frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
	doc = frappe.get_doc(
		{
			"doctype": "Scope Item",
			"code": code,
			"title": f"T {code}",
			"enabled": enabled,
			"erpnext_item": erpnext_item,
		}
	)
	for it in items or []:
		doc.append("erpnext_items", {"item": it})
	doc.insert(ignore_permissions=True)
	return code


class TestScopeItemLinks(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.I1, cls.I2, cls.I3 = _item("_SL-ITEM-1"), _item("_SL-ITEM-2"), _item("_SL-ITEM-3")

	def tearDown(self):
		for c in ("_SL-A", "_SL-B", "_SL-C", "_SL-DIS"):
			if frappe.db.exists("Scope Item", c):
				frappe.delete_doc("Scope Item", c, force=True, ignore_permissions=True)
		frappe.db.commit()  # nosemgrep — limpieza de fixtures de test

	# Child DocType existe y solo contiene el Link requerido.
	def test_child_doctype_solo_link(self):
		meta = frappe.get_meta("Scope Item ERPNext Item")
		self.assertTrue(meta.istable)
		self.assertEqual([f.fieldname for f in meta.fields], ["item"])
		f = meta.get_field("item")
		self.assertEqual((f.fieldtype, f.options, bool(f.reqd)), ("Link", "Item", True))

	# 1. resolver: legacy solamente.
	def test_resolver_legacy(self):
		_scope("_SL-A", erpnext_item=self.I1)
		self.assertEqual(links.resolve_scope_items_for_item(self.I1), ["_SL-A"])

	# 2. resolver: child solamente.
	def test_resolver_child(self):
		_scope("_SL-A", items=[self.I1])
		self.assertEqual(links.resolve_scope_items_for_item(self.I1), ["_SL-A"])

	# 3. resolver: legacy + child sin duplicar.
	def test_resolver_union_dedup(self):
		_scope("_SL-A", erpnext_item=self.I1, items=[self.I1])
		self.assertEqual(links.resolve_scope_items_for_item(self.I1), ["_SL-A"])

	# 4. un Scope Item con varios Items (child).
	def test_scope_varios_items(self):
		_scope("_SL-A", items=[self.I1, self.I2, self.I3])
		got = {r.item for r in frappe.get_doc("Scope Item", "_SL-A").erpnext_items}
		self.assertEqual(got, {self.I1, self.I2, self.I3})

	# 5. un Item con varios Scope Items.
	def test_item_varios_scopes(self):
		_scope("_SL-A", items=[self.I1])
		_scope("_SL-B", erpnext_item=self.I1)  # uno por child, otro por legacy
		self.assertEqual(set(links.resolve_scope_items_for_item(self.I1)), {"_SL-A", "_SL-B"})

	# no se permiten duplicados dentro del mismo Scope Item.
	def test_no_duplicados(self):
		with self.assertRaises(frappe.ValidationError):
			_scope("_SL-A", items=[self.I1, self.I1])

	# 6. desde Item, quitar limpia el legacy correctamente sin tocar otras relaciones.
	def test_set_quita_legacy_y_conserva_otros(self):
		# Scope A: legacy erpnext_item = I1, child I2.
		_scope("_SL-A", erpnext_item=self.I1, items=[self.I2])
		# Usuario abre I1 y quita Scope A (deja selección vacía para I1).
		links.set_scope_items_for_item(self.I1, [])
		a = frappe.get_doc("Scope Item", "_SL-A")
		self.assertIsNone(a.erpnext_item)  # legacy limpiado (apuntaba a I1)
		self.assertEqual({r.item for r in a.erpnext_items}, {self.I2})  # child I2 permanece
		self.assertEqual(links.resolve_scope_items_for_item(self.I1), [])
		self.assertEqual(links.resolve_scope_items_for_item(self.I2), ["_SL-A"])

	# get API devuelve la unión.
	def test_get_api_union(self):
		_scope("_SL-A", items=[self.I1])
		_scope("_SL-B", erpnext_item=self.I1)
		self.assertEqual({r["name"] for r in links.get_scope_items_for_item(self.I1)}, {"_SL-A", "_SL-B"})

	# set: agrega, quita solo la relación de ESE Item, conserva otras.
	def test_set_aislado_por_item(self):
		_scope("_SL-A", items=[self.I1, self.I2])
		_scope("_SL-B", items=[self.I1])
		links.set_scope_items_for_item(self.I1, ["_SL-B"])
		self.assertEqual({r.item for r in frappe.get_doc("Scope Item", "_SL-A").erpnext_items}, {self.I2})
		self.assertEqual({r.item for r in frappe.get_doc("Scope Item", "_SL-B").erpnext_items}, {self.I1})

	# Scope Items disabled no pueden agregarse por API.
	def test_disabled_no_se_agrega(self):
		_scope("_SL-DIS", enabled=0)
		with self.assertRaises(frappe.ValidationError):
			links.set_scope_items_for_item(self.I1, ["_SL-DIS"])
		self.assertEqual(links.resolve_scope_items_for_item(self.I1), [])


if __name__ == "__main__":
	unittest.main()
