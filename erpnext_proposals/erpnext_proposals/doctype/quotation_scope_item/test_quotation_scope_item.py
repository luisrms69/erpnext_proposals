import unittest

import frappe


class TestQuotationScopeItem(unittest.TestCase):
	def test_no_price_fields(self):
		"""Child table must never carry price, cost or rate fields.

		Excluded: Section Break / Column Break field types (they are UI organizers,
		not data fields), and the internal cost snapshot fields (costing_rate,
		rate_source, rate_locked, rate_locked_on) which are read-only, print_hide=1
		and only used for internal profitability — never shown in the commercial PDF.
		"""
		meta = frappe.get_meta("Quotation Scope Item")
		internal_snapshot_fields = {"costing_rate", "rate_source", "rate_locked", "rate_locked_on"}
		# Bandera booleana de control (no es campo comercial).
		control_flags = {"is_internal_cost_task"}
		layout_types = {"Section Break", "Column Break", "Tab Break"}
		field_names = [
			f.fieldname
			for f in meta.fields
			if f.fieldname not in internal_snapshot_fields
			and f.fieldname not in control_flags
			and f.fieldtype not in layout_types
		]
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
