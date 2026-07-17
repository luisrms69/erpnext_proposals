import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.phases import (
	cleanup_test_phases,
	ensure_test_phases,
)


class TestScopeItem(unittest.TestCase):
	def test_create(self):
		doc = frappe.get_doc(
			{
				"doctype": "Scope Item",
				"code": "_TEST-001",
				"title": "Test Scope Item",
				"description": "<p>Descripción de prueba.</p>",
				"deliverable": "<p>Entregable de prueba.</p>",
			}
		)
		doc.insert()
		self.assertEqual(doc.name, "_TEST-001")
		doc.delete()

	def test_mandatory_code(self):
		doc = frappe.get_doc(
			{
				"doctype": "Scope Item",
				"title": "Sin código",
			}
		)
		with self.assertRaises(frappe.exceptions.ValidationError):
			doc.insert()

	def test_mandatory_title(self):
		doc = frappe.get_doc(
			{
				"doctype": "Scope Item",
				"code": "_TEST-NOTITLE",
			}
		)
		with self.assertRaises(frappe.exceptions.ValidationError):
			doc.insert()

	def test_create_with_erpnext_item(self):
		item_code = "_TEST-SCOPE-REF-ITEM"

		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
			frappe.db.commit()
			frappe.clear_cache()

		if not frappe.db.exists("Item Group", "All Item Groups"):
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": "All Item Groups",
					"is_group": 1,
				}
			).insert(ignore_permissions=True)
			frappe.db.commit()

		item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		if not item_group:
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": "_Test Item Group",
					"is_group": 0,
					"parent_item_group": "All Item Groups",
				}
			).insert(ignore_permissions=True)
			frappe.db.commit()
			item_group = "_Test Item Group"

		if not frappe.db.exists("Item", item_code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": item_code,
					"item_name": "_Test Item Scope Ref",
					"item_group": item_group,
					"stock_uom": "Nos",
					"is_sales_item": 1,
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)

		created_phases = ensure_test_phases()
		doc = frappe.get_doc(
			{
				"doctype": "Scope Item",
				"code": "_TEST-SC-WITHITEM",
				"title": "_Test With ERPNext Item",
				"erpnext_item": item_code,
				"phase": "DISC",
				"description": "<p>Descripción de prueba</p>",
				"deliverable": "<p>Entregable de prueba</p>",
				"estimated_hours": 8.0,
			}
		)
		doc.insert(ignore_permissions=True)

		self.assertEqual(doc.erpnext_item, item_code)
		self.assertEqual(doc.phase, "DISC")
		self.assertEqual(doc.description, "<p>Descripción de prueba</p>")
		self.assertEqual(doc.deliverable, "<p>Entregable de prueba</p>")
		self.assertEqual(doc.estimated_hours, 8.0)
		doc.delete()
		cleanup_test_phases(created_phases)

	def test_no_price_fields(self):
		meta = frappe.get_meta("Scope Item")
		# Banderas booleanas de control que contienen una palabra prohibida pero NO son campos
		# comerciales (no representan precio/costo).
		allowed = {"is_internal_cost_task"}
		field_names = [f.fieldname for f in meta.fields if f.fieldname not in allowed]
		forbidden = {"rate", "price", "cost", "amount", "margin"}
		for fname in field_names:
			parts = set(fname.split("_"))
			overlap = parts & forbidden
			self.assertFalse(overlap, f"Campo comercial encontrado en Scope Item: {fname}")
