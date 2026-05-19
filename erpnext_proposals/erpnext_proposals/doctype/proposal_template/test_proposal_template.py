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

	def test_custom_title_and_content(self):
		section = frappe.get_doc(
			{
				"doctype": "Proposal Section",
				"section_name": "_Test Section For Custom",
				"section_type": "Personalizado",
				"content": "<p>Original content</p>",
			}
		)
		section.insert(ignore_permissions=True)

		doc = frappe.get_doc(
			{
				"doctype": "Proposal Template",
				"template_name": "_Test Template Custom",
				"sections": [
					{
						"proposal_section": section.name,
						"custom_title": "Mi Título Personalizado",
						"use_custom_content": 1,
						"custom_content": "<p>Contenido override</p>",
						"include_by_default": 1,
					}
				],
			}
		)
		doc.insert(ignore_permissions=True)

		row = doc.sections[0]
		self.assertEqual(row.custom_title, "Mi Título Personalizado")
		self.assertEqual(row.use_custom_content, 1)
		self.assertEqual(row.custom_content, "<p>Contenido override</p>")

		doc.delete()
		section.delete()

	def test_mandatory_template_name(self):
		doc = frappe.get_doc({"doctype": "Proposal Template"})
		with self.assertRaises(frappe.exceptions.ValidationError):
			doc.insert()
