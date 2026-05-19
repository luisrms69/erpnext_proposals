import unittest

import frappe


class TestProposalTemplate(unittest.TestCase):
	def test_create(self):
		doc = frappe.get_doc(
			{
				"doctype": "Proposal Template",
				"template_name": "_Test Template",
				"description": "Template de prueba",
			}
		)
		doc.insert()
		self.assertEqual(doc.name, "_Test Template")
		doc.delete()

	def test_auto_sequence(self):
		doc = frappe.get_doc(
			{
				"doctype": "Proposal Template",
				"template_name": "_Test Template Sequence",
				"sections": [
					{"proposal_section": "_Test Section A"},
					{"proposal_section": "_Test Section B"},
					{"proposal_section": "_Test Section C"},
				],
			}
		)
		doc.validate()
		seqs = [row.sequence for row in doc.sections]
		self.assertEqual(seqs, [10, 20, 30])

	def test_sequence_respects_existing(self):
		doc = frappe.get_doc(
			{
				"doctype": "Proposal Template",
				"template_name": "_Test Template Seq Gap",
				"sections": [
					{"proposal_section": "_Test Section A", "sequence": 50},
					{"proposal_section": "_Test Section B"},
				],
			}
		)
		doc.validate()
		seqs = [row.sequence for row in doc.sections]
		self.assertEqual(seqs, [50, 60])

	def test_mandatory_template_name(self):
		doc = frappe.get_doc({"doctype": "Proposal Template"})
		with self.assertRaises(frappe.exceptions.ValidationError):
			doc.insert()
