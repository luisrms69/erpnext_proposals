import unittest

import frappe


class TestProposalCostMatrixLog(unittest.TestCase):
    def test_create(self):
        designation = frappe.db.get_value("Designation", {}, "name")
        if not designation:
            self.skipTest("No Designation records available")

        doc = frappe.get_doc(
            {
                "doctype": "Proposal Cost Matrix Log",
                "designation": designation,
                "old_rate": 0.0,
                "new_rate": 500.0,
                "source": "activity_cost",
                "employee_count": 1,
                "changed_on": frappe.utils.now_datetime(),
                "rebuild_run_id": "REBUILD-TEST",
                "notes": "Primera vez",
            }
        )
        doc.insert(ignore_permissions=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Proposal Cost Matrix Log", doc.name, ignore_permissions=True)

    def test_required_designation(self):
        doc = frappe.get_doc({"doctype": "Proposal Cost Matrix Log"})
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert()
