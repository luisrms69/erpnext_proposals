import frappe
import pytest


class TestScopeItem:
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
		assert doc.name == "_TEST-001"
		doc.delete()

	def test_mandatory_code(self):
		doc = frappe.get_doc(
			{
				"doctype": "Scope Item",
				"title": "Sin código",
			}
		)
		with pytest.raises(frappe.exceptions.MandatoryError):
			doc.insert()

	def test_mandatory_title(self):
		doc = frappe.get_doc(
			{
				"doctype": "Scope Item",
				"code": "_TEST-NOTITLE",
			}
		)
		with pytest.raises(frappe.exceptions.MandatoryError):
			doc.insert()

	def test_no_price_fields(self):
		doc = frappe.get_doc(
			{
				"doctype": "Scope Item",
				"code": "_TEST-002",
				"title": "Test sin precios",
			}
		)
		# Ningún campo debe tener 'rate', 'price', 'cost', 'amount' o 'margin'
		field_names = [f.fieldname for f in doc.meta.fields]
		forbidden = ("rate", "price", "cost", "amount", "margin")
		for fname in field_names:
			assert not any(f in fname for f in forbidden), (
				f"Campo comercial encontrado en Scope Item: {fname}"
			)
