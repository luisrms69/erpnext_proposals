import unittest

import frappe


class TestCreateProjectFromQuotation(unittest.TestCase):
	"""
	Tests for create_project_from_quotation.

	Integration tests requiring full ERPNext setup (Company, Customer,
	Cost Center, Quotation with Scope Items) are validated manually on
	proposals.dev. Only validation-path tests are included here.
	"""

	def test_raises_if_not_submitted(self):
		"""Non-submitted Quotation raises ValidationError."""
		from erpnext_proposals.erpnext_proposals.utils.project import (
			create_project_from_quotation,
		)

		# Insert a draft Quotation row directly for the check
		name = "_TEST-QTN-DRAFT-PROJ"
		frappe.db.sql("INSERT IGNORE INTO `tabQuotation` (name, docstatus) VALUES (%s, 0)", (name,))
		frappe.db.commit()
		try:
			with self.assertRaises(frappe.exceptions.ValidationError):
				create_project_from_quotation(name)
		finally:
			frappe.db.sql("DELETE FROM `tabQuotation` WHERE name=%s", (name,))
			frappe.db.commit()

	def test_raises_without_proposal_template(self):
		"""Submitted Quotation without proposal_template raises ValidationError."""
		from erpnext_proposals.erpnext_proposals.utils.project import (
			create_project_from_quotation,
		)

		name = "_TEST-QTN-NOTMPL-PROJ"
		frappe.db.sql(
			"INSERT IGNORE INTO `tabQuotation` (name, docstatus, proposal_template) VALUES (%s, 1, NULL)",
			(name,),
		)
		frappe.db.commit()
		try:
			with self.assertRaises(frappe.exceptions.ValidationError):
				create_project_from_quotation(name)
		finally:
			frappe.db.sql("DELETE FROM `tabQuotation` WHERE name=%s", (name,))
			frappe.db.commit()

	def test_raises_without_scope_items(self):
		"""Submitted Quotation with template but no scope items raises ValidationError."""
		from erpnext_proposals.erpnext_proposals.utils.project import (
			create_project_from_quotation,
		)

		name = "_TEST-QTN-NOSCOPE-PROJ"
		frappe.db.sql(
			"INSERT IGNORE INTO `tabQuotation` (name, docstatus, proposal_template) VALUES (%s, 1, '_Test Template')",
			(name,),
		)
		frappe.db.commit()
		try:
			with self.assertRaises(frappe.exceptions.ValidationError):
				create_project_from_quotation(name)
		finally:
			frappe.db.sql("DELETE FROM `tabQuotation` WHERE name=%s", (name,))
			frappe.db.commit()
