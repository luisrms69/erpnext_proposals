import frappe
from frappe import _


class QuotationProposalMixin:
	def declare_enquiry_lost(self, *args, **kwargs):
		if self.get("proposal_group"):
			frappe.throw(
				_(
					"No se puede marcar como perdida una propuesta con flujo de revisión. "
					"Usa el workflow de propuestas para gestionar el estado de la propuesta."
				)
			)
		return super().declare_enquiry_lost(*args, **kwargs)
