import frappe
import pytest


class TestQuotationScopeItem:
	def test_no_price_fields(self):
		"""Child table must never carry price, cost or rate fields."""
		meta = frappe.get_meta("Quotation Scope Item")
		field_names = [f.fieldname for f in meta.fields]
		forbidden = ("rate", "price", "cost", "amount", "margin")
		for fname in field_names:
			assert not any(f in fname for f in forbidden), (
				f"Campo comercial encontrado en Quotation Scope Item: {fname}"
			)

	def test_is_child_table(self):
		meta = frappe.get_meta("Quotation Scope Item")
		assert meta.istable == 1

	def test_required_fields_exist(self):
		meta = frappe.get_meta("Quotation Scope Item")
		field_names = [f.fieldname for f in meta.fields]
		for expected in (
			"scope_item",
			"code",
			"title",
			"include_in_proposal",
			"description",
			"deliverable",
			"phase",
			"erpnext_item",
			"estimated_hours",
			"activity_type",
			"designation",
		):
			assert expected in field_names, f"Campo faltante: {expected}"
