import frappe
import pytest


class TestProposalSection:
	def test_create(self):
		doc = frappe.get_doc(
			{
				"doctype": "Proposal Section",
				"section_name": "_Test Section",
				"section_type": "Objetivo",
				"content": "<p>Contenido de prueba.</p>",
			}
		)
		doc.insert()
		assert doc.name == "_Test Section"
		doc.delete()

	def test_title_defaults_to_section_name(self):
		doc = frappe.get_doc(
			{
				"doctype": "Proposal Section",
				"section_name": "_Test Title Default",
				"section_type": "Personalizado",
			}
		)
		doc.insert()
		assert doc.title == "_Test Title Default"
		doc.delete()

	def test_mandatory_section_name(self):
		doc = frappe.get_doc(
			{
				"doctype": "Proposal Section",
				"section_type": "Objetivo",
			}
		)
		with pytest.raises(frappe.exceptions.MandatoryError):
			doc.insert()
