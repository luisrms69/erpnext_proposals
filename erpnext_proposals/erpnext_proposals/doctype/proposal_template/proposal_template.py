import frappe
from frappe.model.document import Document


class ProposalTemplate(Document):
	def validate(self):
		self._auto_assign_sequence()

	def _auto_assign_sequence(self):
		# Rows with a sequence already set
		assigned = sorted(row.sequence for row in self.sections if row.sequence)
		next_seq = (max(assigned) + 10) if assigned else 10

		for row in self.sections:
			if not row.sequence:
				row.sequence = next_seq
				next_seq += 10
