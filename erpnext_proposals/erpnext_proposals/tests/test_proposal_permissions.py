"""
Tests for assert_can_manage_proposals role guard and endpoint protection.

Two classes:
- TestProposalPermissionsHelper — unit tests on the guard directly.
- TestEndpointPermissionGuards  — confirms the guard fires before any side effect
  in each critical whitelisted endpoint.
"""

import unittest
from unittest.mock import patch

import frappe

from erpnext_proposals.erpnext_proposals.utils.permissions import assert_can_manage_proposals


class TestProposalPermissionsHelper(unittest.TestCase):
	"""assert_can_manage_proposals must allow System Manager and Proposals Manager only."""

	def test_proposals_manager_passes(self):
		with patch("frappe.get_roles", return_value=["Proposals Manager"]):
			assert_can_manage_proposals()

	def test_system_manager_passes(self):
		with patch("frappe.get_roles", return_value=["System Manager"]):
			assert_can_manage_proposals()

	def test_proposals_manager_with_extra_roles_passes(self):
		with patch("frappe.get_roles", return_value=["Proposals Manager", "Proposals User", "Sales User"]):
			assert_can_manage_proposals()

	def test_proposals_user_blocked(self):
		with patch("frappe.get_roles", return_value=["Proposals User"]):
			with self.assertRaises(frappe.PermissionError):
				assert_can_manage_proposals()

	def test_sales_user_blocked(self):
		with patch("frappe.get_roles", return_value=["Sales User"]):
			with self.assertRaises(frappe.PermissionError):
				assert_can_manage_proposals()

	def test_unrelated_roles_blocked(self):
		with patch("frappe.get_roles", return_value=["Employee", "HR User", "Accounts User"]):
			with self.assertRaises(frappe.PermissionError):
				assert_can_manage_proposals()

	def test_empty_roles_blocked(self):
		with patch("frappe.get_roles", return_value=[]):
			with self.assertRaises(frappe.PermissionError):
				assert_can_manage_proposals()


class TestEndpointPermissionGuards(unittest.TestCase):
	"""
	Confirm each endpoint raises PermissionError before any DB access or side effect
	when the caller lacks the required role.

	For allowed roles: confirm the guard passes (any subsequent error must NOT be
	a PermissionError — it will be a business logic or doc-not-found error).
	"""

	def _as_proposals_user(self):
		return patch("frappe.get_roles", return_value=["Proposals User"])

	def _as_proposals_manager(self):
		return patch("frappe.get_roles", return_value=["Proposals Manager"])

	# ── create_new_proposal_version ───────────────────────────────────────────

	def test_create_new_version_blocks_proposals_user(self):
		from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import (
			create_new_proposal_version,
		)

		with self._as_proposals_user():
			with self.assertRaises(frappe.PermissionError):
				create_new_proposal_version("_FAKE-QTN", reason="test")

	def test_create_new_version_proposals_manager_passes_guard(self):
		"""Proposals Manager passes role guard — next error is business logic, not permission."""
		from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import (
			create_new_proposal_version,
		)

		with self._as_proposals_manager():
			try:
				create_new_proposal_version("_FAKE-QTN-NOTEXIST", reason="test")
				self.fail("Expected a post-guard error but none was raised")
			except frappe.PermissionError:
				self.fail("Role guard blocked Proposals Manager — guard should have passed")
			except Exception:
				pass  # Any non-PermissionError confirms the guard passed

	def test_create_new_version_system_manager_passes_guard(self):
		from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import (
			create_new_proposal_version,
		)

		with patch("frappe.get_roles", return_value=["System Manager"]):
			try:
				create_new_proposal_version("_FAKE-QTN-NOTEXIST", reason="test")
				self.fail("Expected a post-guard error but none was raised")
			except frappe.PermissionError:
				self.fail("Role guard blocked System Manager — guard should have passed")
			except Exception:
				pass

	# ── create_project_from_quotation ─────────────────────────────────────────

	def test_create_project_blocks_proposals_user(self):
		from erpnext_proposals.erpnext_proposals.utils.project import (
			create_project_from_quotation,
		)

		with self._as_proposals_user():
			with self.assertRaises(frappe.PermissionError):
				create_project_from_quotation("_FAKE-QTN")

	def test_create_project_proposals_manager_passes_guard(self):
		from erpnext_proposals.erpnext_proposals.utils.project import (
			create_project_from_quotation,
		)

		with self._as_proposals_manager():
			try:
				create_project_from_quotation("_FAKE-QTN-NOTEXIST")
				self.fail("Expected a post-guard error but none was raised")
			except frappe.PermissionError:
				self.fail("Role guard blocked Proposals Manager — guard should have passed")
			except Exception:
				pass

	def test_create_project_system_manager_passes_guard(self):
		from erpnext_proposals.erpnext_proposals.utils.project import (
			create_project_from_quotation,
		)

		with patch("frappe.get_roles", return_value=["System Manager"]):
			try:
				create_project_from_quotation("_FAKE-QTN-NOTEXIST")
				self.fail("Expected a post-guard error but none was raised")
			except frappe.PermissionError:
				self.fail("Role guard blocked System Manager — guard should have passed")
			except Exception:
				pass

	# ── rebuild_cost_matrix ───────────────────────────────────────────────────

	def test_rebuild_cost_matrix_blocks_proposals_user(self):
		from erpnext_proposals.erpnext_proposals.utils.cost_matrix import rebuild_cost_matrix

		with self._as_proposals_user():
			with self.assertRaises(frappe.PermissionError):
				rebuild_cost_matrix()

	def test_rebuild_cost_matrix_blocks_sales_user(self):
		from erpnext_proposals.erpnext_proposals.utils.cost_matrix import rebuild_cost_matrix

		with patch("frappe.get_roles", return_value=["Sales User"]):
			with self.assertRaises(frappe.PermissionError):
				rebuild_cost_matrix()
