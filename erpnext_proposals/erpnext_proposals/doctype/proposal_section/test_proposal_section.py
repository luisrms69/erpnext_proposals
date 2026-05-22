import unittest

import frappe


class TestProposalSection(unittest.TestCase):
	def test_create(self):
		doc = frappe.get_doc(
			{
				"doctype": "Proposal Section",
				"section_name": "_Test Section",
				"content": "<p>Contenido de prueba.</p>",
			}
		)
		doc.insert()
		self.assertEqual(doc.name, "_Test Section")
		doc.delete()

	def test_title_defaults_to_section_name(self):
		doc = frappe.get_doc(
			{
				"doctype": "Proposal Section",
				"section_name": "_Test Title Default",
			}
		)
		doc.insert()
		self.assertEqual(doc.title, "_Test Title Default")
		doc.delete()

	def test_mandatory_section_name(self):
		doc = frappe.get_doc(
			{
				"doctype": "Proposal Section",
			}
		)
		with self.assertRaises(frappe.exceptions.ValidationError):
			doc.insert()
