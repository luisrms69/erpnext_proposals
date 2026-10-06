import unittest

import frappe


class TestProposalCostMatrix(unittest.TestCase):
	def test_create(self):
		designation = frappe.db.get_value("Designation", {}, "name")
		if not designation:
			self.skipTest("No Designation records available")

		if frappe.db.exists("Proposal Cost Matrix", {"designation": designation}):
			self.skipTest("Designation ya tiene tarifa en la matriz")

		doc = frappe.get_doc(
			{
				"doctype": "Proposal Cost Matrix",
				"designation": designation,
				"avg_costing_rate": 500.0,
				"source": "activity_cost",
				"status": "ok",
			}
		)
		doc.insert(ignore_permissions=True)
		self.assertIsNotNone(doc.name)
		frappe.delete_doc("Proposal Cost Matrix", doc.name, ignore_permissions=True)

	def test_required_designation(self):
		doc = frappe.get_doc({"doctype": "Proposal Cost Matrix"})
		with self.assertRaises(frappe.exceptions.MandatoryError):
			doc.insert()

	def test_rebuild_runs_without_error(self):
		from erpnext_proposals.erpnext_proposals.utils.cost_matrix import rebuild_cost_matrix

		result = rebuild_cost_matrix()
		self.assertIn("created", result)
		self.assertIn("updated", result)
		self.assertIn("skipped", result)

	def test_get_designation_cost_no_data(self):
		from erpnext_proposals.erpnext_proposals.utils.cost_matrix import get_designation_cost

		rate, source = get_designation_cost("__nonexistent_designation__")
		self.assertEqual(rate, 0.0)
		self.assertEqual(source, "sin_datos")

	def test_get_designation_cost_resolves_by_designation(self):
		"""Ruta única: la tarifa viene de la Designation en Proposal Cost Matrix (sin Activity Type)."""
		from erpnext_proposals.erpnext_proposals.utils.cost_matrix import get_designation_cost

		d = "__PCM Test Perfil__"
		if not frappe.db.exists("Designation", d):
			frappe.get_doc({"doctype": "Designation", "designation_name": d}).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Cost Matrix", {"designation": d}):
			frappe.get_doc(
				{
					"doctype": "Proposal Cost Matrix",
					"designation": d,
					"avg_costing_rate": 777.0,
					"status": "ok",
				}
			).insert(ignore_permissions=True)
		rate, source = get_designation_cost(d)
		self.assertEqual(rate, 777.0)
		self.assertEqual(source, "matrix")
