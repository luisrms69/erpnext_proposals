# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ProposalSettings(Document):
	def validate(self) -> None:
		self._assert_unique_per_company()

	def _assert_unique_per_company(self) -> None:
		"""Como máximo un Proposal Settings por Company (ADR-0017, Fase 1 bis). Genérico y robusto: además
		del autoname `field:company` (unicidad a nivel de nombre/DB), validamos explícitamente para dar un
		mensaje claro en cualquier sitio multi-company."""
		if not self.company:
			return
		filters = {"company": self.company}
		if not self.is_new():
			# En una edición, excluir el propio registro (el autoname `field:company` hace name == company).
			filters["name"] = ["!=", self.name]
		if frappe.db.exists("Proposal Settings", filters):
			frappe.throw(
				_("Ya existe una configuración de propuestas para la compañía {0}.").format(self.company),
				title=_("Configuración duplicada"),
			)
