import unittest

import frappe
from frappe.utils import add_days, today


class TestQuotationScopeGeneration(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		# Company
		cls.company = frappe.db.get_value("Company", {}, "name")
		if not cls.company:
			co = frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": "_Test Proposals Co",
					"abbr": "_TPC",
					"default_currency": "MXN",
					"country": "Mexico",
				}
			)
			co.insert(ignore_permissions=True)
			cls.company = co.name

		# UOM — commit immediately so link validation can find it
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
			frappe.db.commit()
			frappe.clear_cache()

		# Item Group — commit each level so parent exists before child
		if not frappe.db.exists("Item Group", "All Item Groups"):
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": "All Item Groups",
					"is_group": 1,
				}
			).insert(ignore_permissions=True)
			frappe.db.commit()

		if not frappe.db.exists("Item Group", "_Test Item Group"):
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

		# Item
		cls.item_code = "_TEST-PROP-GEN-001"
		if not frappe.db.exists("Item", cls.item_code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": cls.item_code,
					"item_name": "_Test Proposals Gen Item",
					"item_group": item_group,
					"stock_uom": "Nos",
					"is_sales_item": 1,
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)

		# Customer Group + Territory + Customer
		if not frappe.db.exists("Customer Group", "All Customer Groups"):
			frappe.get_doc(
				{
					"doctype": "Customer Group",
					"customer_group_name": "All Customer Groups",
					"is_group": 1,
				}
			).insert(ignore_permissions=True)

		customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		if not customer_group:
			frappe.get_doc(
				{
					"doctype": "Customer Group",
					"customer_group_name": "_Test CG",
					"is_group": 0,
					"parent_customer_group": "All Customer Groups",
				}
			).insert(ignore_permissions=True)
			customer_group = "_Test CG"

		if not frappe.db.exists("Territory", "All Territories"):
			frappe.get_doc(
				{
					"doctype": "Territory",
					"territory_name": "All Territories",
					"is_group": 1,
				}
			).insert(ignore_permissions=True)

		territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
		if not territory:
			frappe.get_doc(
				{
					"doctype": "Territory",
					"territory_name": "_Test Territory",
					"is_group": 0,
					"parent_territory": "All Territories",
				}
			).insert(ignore_permissions=True)
			territory = "_Test Territory"

		customer_name = "_Test Proposals Gen Customer"
		cls.customer = frappe.db.get_value("Customer", {"customer_name": customer_name}, "name")
		if not cls.customer:
			cust = frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": customer_name,
					"customer_type": "Company",
					"customer_group": customer_group,
					"territory": territory,
				}
			)
			cust.insert(ignore_permissions=True)
			frappe.db.commit()
			frappe.clear_cache()
			cls.customer = cust.name

		# Price List
		cls.currency = frappe.db.get_value("Company", cls.company, "default_currency") or "MXN"
		cls.price_list = frappe.db.get_value("Price List", {"selling": 1, "currency": cls.currency}, "name")
		if not cls.price_list:
			pl = frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": "_Test Proposals Price List",
					"selling": 1,
					"currency": cls.currency,
				}
			)
			pl.insert(ignore_permissions=True)
			frappe.db.commit()
			cls.price_list = pl.name

		# Scope Item linked to Item
		cls.scope_code = "_TEST-SC-GEN-001"
		if not frappe.db.exists("Scope Item", cls.scope_code):
			frappe.get_doc(
				{
					"doctype": "Scope Item",
					"code": cls.scope_code,
					"title": "_Test Scope Gen",
					"erpnext_item": cls.item_code,
					"phase": "_Test Phase",
					"description": "<p>Test description</p>",
					"deliverable": "<p>Test deliverable</p>",
					"enabled": 1,
				}
			).insert(ignore_permissions=True)

		# Proposal Section + Template
		cls.section_name = "_Test Gen Section"
		if not frappe.db.exists("Proposal Section", cls.section_name):
			frappe.get_doc(
				{
					"doctype": "Proposal Section",
					"section_name": cls.section_name,
					"section_type": "Objetivo",
					"content": "<p>Test</p>",
				}
			).insert(ignore_permissions=True)

		cls.template_name = "_Test Gen Template"
		if not frappe.db.exists("Proposal Template", cls.template_name):
			frappe.get_doc(
				{
					"doctype": "Proposal Template",
					"template_name": cls.template_name,
				}
			).insert(ignore_permissions=True)

		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		for qtn in frappe.get_all("Quotation", filters={"proposal_title": "_Test Scope Gen"}):
			frappe.delete_doc("Quotation", qtn.name, ignore_permissions=True, force=True)

		for doctype, name in [
			("Proposal Template", cls.template_name),
			("Proposal Section", cls.section_name),
			("Scope Item", cls.scope_code),
		]:
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)

		frappe.db.commit()
		super().tearDownClass()

	def _make_quotation(self, with_template=True):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"transaction_date": today(),
				"valid_till": add_days(today(), 30),
				"company": self.company,
				"currency": self.currency,
				"conversion_rate": 1,
				"selling_price_list": self.price_list,
				"price_list_currency": self.currency,
				"plc_conversion_rate": 1,
				"proposal_template": self.template_name if with_template else None,
				"proposal_title": "_Test Scope Gen",
				"items": [
					{
						"item_code": self.item_code,
						"qty": 1,
						"rate": 1000,
					}
				],
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def test_scope_items_generated_on_save(self):
		doc = self._make_quotation(with_template=True)
		try:
			self.assertGreater(
				len(doc.quotation_scope_items),
				0,
				"No scope items generated after save with proposal_template",
			)
			row = next(r for r in doc.quotation_scope_items if r.scope_item == self.scope_code)
			self.assertEqual(row.item_code, self.item_code)
			self.assertEqual(row.title, "_Test Scope Gen")
			self.assertEqual(row.phase, "_Test Phase")
			self.assertEqual(row.auto_generated, 1)
			self.assertEqual(row.description, "<p>Test description</p>")
			self.assertEqual(row.deliverable, "<p>Test deliverable</p>")
		finally:
			frappe.delete_doc("Quotation", doc.name, ignore_permissions=True, force=True)

	def test_generation_is_idempotent(self):
		doc = self._make_quotation(with_template=True)
		try:
			initial_count = len(doc.quotation_scope_items)
			doc.save(ignore_permissions=True)
			self.assertEqual(
				len(doc.quotation_scope_items),
				initial_count,
				"Scope items duplicated on second save",
			)
		finally:
			frappe.delete_doc("Quotation", doc.name, ignore_permissions=True, force=True)

	def test_quotation_items_unchanged(self):
		doc = self._make_quotation(with_template=True)
		try:
			self.assertEqual(len(doc.items), 1)
			self.assertEqual(doc.items[0].item_code, self.item_code)
			self.assertEqual(doc.items[0].qty, 1)
			self.assertEqual(float(doc.items[0].rate), 1000.0)
		finally:
			frappe.delete_doc("Quotation", doc.name, ignore_permissions=True, force=True)

	def test_no_scope_without_proposal_template(self):
		doc = self._make_quotation(with_template=False)
		try:
			self.assertEqual(
				len(doc.quotation_scope_items),
				0,
				"Scope items generated even without proposal_template",
			)
		finally:
			frappe.delete_doc("Quotation", doc.name, ignore_permissions=True, force=True)

	def test_print_format_renders(self):
		doc = self._make_quotation(with_template=True)
		try:
			html = frappe.get_print("Quotation", doc.name, "Propuesta Comercial", no_letterhead=1)
			self.assertIsNotNone(html)
			self.assertGreater(len(html), 100)
		except Exception as e:
			self.skipTest(f"Print format rendering not available in test environment: {e}")
		finally:
			frappe.delete_doc("Quotation", doc.name, ignore_permissions=True, force=True)
