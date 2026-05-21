import unittest

import frappe


class TestProposalCostMatrix(unittest.TestCase):
    def test_create(self):
        designation = frappe.db.get_value("Designation", {}, "name")
        if not designation:
            self.skipTest("No Designation records available")

        doc = frappe.get_doc(
            {
                "doctype": "Proposal Cost Matrix",
                "designation": designation,
                "is_general_rate": 1,
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

        rate, source = get_designation_cost("__nonexistent_designation__", None)
        self.assertEqual(rate, 0.0)
        self.assertEqual(source, "sin_datos")

    def test_get_designation_cost_fallback_activity_type(self):
        from erpnext_proposals.erpnext_proposals.utils.cost_matrix import get_designation_cost

        # With no designation but a valid activity_type that has a rate,
        # should fall back to activity_type costing_rate
        at = frappe.db.get_value("Activity Type", {"costing_rate": [">", 0]}, "name")
        if not at:
            self.skipTest("No Activity Type with costing_rate > 0")

        rate, source = get_designation_cost(None, at)
        self.assertEqual(source, "activity_type")
        self.assertGreater(rate, 0)
