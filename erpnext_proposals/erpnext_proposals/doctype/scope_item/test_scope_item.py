import unittest

import frappe


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

	def test_no_price_fields(self):
		meta = frappe.get_meta("Scope Item")
		field_names = [f.fieldname for f in meta.fields]
		forbidden = {"rate", "price", "cost", "amount", "margin"}
		for fname in field_names:
			parts = set(fname.split("_"))
			overlap = parts & forbidden
			self.assertFalse(overlap, f"Campo comercial encontrado en Scope Item: {fname}")
