import unittest

import frappe


class _MockItem:
	"""Simple mock for SO item rows — avoids frappe._dict.items() conflict."""

	def __init__(self, prevdoc_docname=None, cost_center=None):
		self.prevdoc_docname = prevdoc_docname
		self.cost_center = cost_center


class _MockSO:
	"""Simple mock for Sales Order doc — avoids frappe._dict.items() conflict."""

	def __init__(self, project=None, cost_center=None, items=None):
		self.project = project
		self.cost_center = cost_center
		self.items = items or []


class TestSalesOrderSync(unittest.TestCase):
	def test_sync_skips_without_prevdoc(self):
		"""No-op when SO items have no prevdoc_docname."""
		from erpnext_proposals.erpnext_proposals.utils.sales_order import (
			_sync_project_from_quotation,
		)

		so = _MockSO(items=[_MockItem(prevdoc_docname=None)])
		_sync_project_from_quotation(so)
		self.assertIsNone(so.project)

	def test_sync_skips_when_project_already_set(self):
		"""SO.project is not overwritten if already set."""
		from erpnext_proposals.erpnext_proposals.utils.sales_order import (
			_sync_project_from_quotation,
		)

		so = _MockSO(project="EXISTING-PROJECT", items=[_MockItem(prevdoc_docname="_TEST-QTN")])
		_sync_project_from_quotation(so)
		self.assertEqual(so.project, "EXISTING-PROJECT")

	def test_sync_fills_cost_center_on_items(self):
		"""SO items get cost_center from Quotation when not already set."""
		from erpnext_proposals.erpnext_proposals.utils.sales_order import (
			_sync_project_from_quotation,
		)

		quotation_name = "_TEST-QTN-CC-SYNC"
		fake_cc = "_Test Cost Center"

		# Insert minimal Quotation row directly
		frappe.db.sql(
			"INSERT IGNORE INTO `tabQuotation` (name, docstatus, proposal_cost_center) VALUES (%s, 1, %s)",
			(quotation_name, fake_cc),
		)
		frappe.db.commit()  # nosemgrep — test isolation requires explicit commit

		item = _MockItem(prevdoc_docname=quotation_name, cost_center=None)
		so = _MockSO(cost_center=None, items=[item])

		_sync_project_from_quotation(so)

		# cost_center should be filled from Quotation
		self.assertEqual(so.cost_center, fake_cc)
		self.assertEqual(item.cost_center, fake_cc)

		# Cleanup
		frappe.db.sql("DELETE FROM `tabQuotation` WHERE name=%s", (quotation_name,))
		frappe.db.commit()  # nosemgrep — test cleanup
