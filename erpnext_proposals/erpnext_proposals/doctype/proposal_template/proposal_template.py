import frappe
from frappe.model.document import Document

from erpnext_proposals.erpnext_proposals.utils.print_format import assert_assignable_print_format


class ProposalTemplate(Document):
	def validate(self):
		self._auto_assign_sequence()
		# Misma validación de servidor compartida con Quotation.proposal_print_format: impide ADOPTAR un
		# Print Format no elegible por API/import/script; no invalida una referencia previa no modificada.
		assert_assignable_print_format(self, "print_format")

	def _auto_assign_sequence(self):
		# Rows with a sequence already set
		assigned = sorted(row.sequence for row in self.sections if row.sequence)
		next_seq = (max(assigned) + 10) if assigned else 10

		for row in self.sections:
			if not row.sequence:
				row.sequence = next_seq
				next_seq += 10
