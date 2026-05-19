import unittest

import frappe


class TestQuotationScopeItem(unittest.TestCase):
	def test_no_price_fields(self):
		"""Child table must never carry price, cost or rate fields."""
		meta = frappe.get_meta("Quotation Scope Item")
		field_names = [f.fieldname for f in meta.fields]
		forbidden = {"rate", "price", "cost", "amount", "margin"}
		for fname in field_names:
			parts = set(fname.split("_"))
			overlap = parts & forbidden
			self.assertFalse(
				overlap,
				f"Campo comercial encontrado en Quotation Scope Item: {fname}",
			)

	def test_is_child_table(self):
		meta = frappe.get_meta("Quotation Scope Item")
		self.assertEqual(meta.istable, 1)

	def test_required_fields_exist(self):
		meta = frappe.get_meta("Quotation Scope Item")
		field_names = [f.fieldname for f in meta.fields]
		for expected in (
			"scope_item",
			"item_code",
			"code",
			"title",
			"include_in_proposal",
			"auto_generated",
			"description",
			"deliverable",
			"phase",
			"estimated_hours",
			"activity_type",
			"designation",
		):
			self.assertIn(expected, field_names, f"Campo faltante: {expected}")
