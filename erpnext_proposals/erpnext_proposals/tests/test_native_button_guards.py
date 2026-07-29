"""
Tests for backend guards on native ERPNext buttons blocked on proposals.

Verifies that declare_enquiry_lost is blocked on Quotations that belong
to the proposal workflow (have proposal_group set).
"""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)


class TestNativeButtonGuards(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from erpnext_proposals.erpnext_proposals.tests.company import (
			get_test_company,
			get_test_item_group,
		)

		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company found.")

		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		if not cg:
			raise unittest.SkipTest("No Customer Group found.")

		cls._created_fy = ensure_current_fiscal_year()

		terr = frappe.db.get_value("Territory", {"is_group": 0}, "name")

		if not frappe.db.exists("Customer", "_Test Guard Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test Guard Customer",
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test Guard Customer"

		ig = get_test_item_group()
		if not frappe.db.exists("Item", "_Test Guard Item"):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "_Test Guard Item",
					"item_name": "_Test Guard Item",
					"item_group": ig,
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
		cls.item = "_Test Guard Item"

		if not frappe.db.exists("Proposal Template", "_Test Guard Template"):
			frappe.get_doc(
				{
					"doctype": "Proposal Template",
					"template_name": "_Test Guard Template",
					"description": "Template for guard tests",
				}
			).insert(ignore_permissions=True)
		cls.proposal_template = "_Test Guard Template"
		cls._created_quotations = []

	@classmethod
	def tearDownClass(cls):
		for name in cls._created_quotations:
			if frappe.db.exists("Quotation", name):
				try:
					doc = frappe.get_doc("Quotation", name)
					if doc.docstatus == 1:
						doc.flags.ignore_linked_doctypes = True
						doc.cancel()
					frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
				except Exception:
					pass
		cleanup_fiscal_year(getattr(cls, "_created_fy", None))

	def _make_submitted_proposal(self):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": f"TEST-GUARD-{frappe.generate_hash(length=6)}",
				"proposal_template": self.proposal_template,
				"proposal_title": "Test Guard Proposal",
				"items": [
					{
						"item_code": self.item,
						"item_name": "_Test Guard Item",
						"qty": 1,
						"rate": 1000,
						"uom": "Nos",
					}
				],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		self._created_quotations.append(doc.name)
		return doc

	def test_declare_enquiry_lost_blocked_on_proposal(self):
		"""declare_enquiry_lost must raise ValidationError on proposals with proposal_group."""
		doc = self._make_submitted_proposal()
		with self.assertRaises(frappe.exceptions.ValidationError):
			doc.declare_enquiry_lost([], [])

	def test_declare_enquiry_lost_mixin_does_not_affect_non_proposal(self):
		"""Mixin must not block quotations without proposal_group."""
		doc = self._make_submitted_proposal()
		doc.proposal_group = None  # simulate non-proposal in memory only
		try:
			doc.declare_enquiry_lost([], [])
		except frappe.exceptions.ValidationError as e:
			self.assertNotIn(
				"flujo de revisión",
				str(e),
				"Mixin incorrectly blocked a quotation without proposal_group",
			)
		except Exception:
			pass  # other ERPNext validation errors are acceptable
