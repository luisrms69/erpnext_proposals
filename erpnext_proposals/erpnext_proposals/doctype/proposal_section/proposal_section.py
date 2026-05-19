import frappe
from frappe.model.document import Document


class ProposalSection(Document):
	def validate(self):
		if not self.title:
			self.title = self.section_name
