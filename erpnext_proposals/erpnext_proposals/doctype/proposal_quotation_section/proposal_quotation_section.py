# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ProposalQuotationSection(Document):
	"""Sección narrativa MATERIALIZADA dentro de la Quotation (child table).

	Reemplaza a `proposal_sections_snapshot` (JSON oculto) para propuestas nuevas: cada fila es una
	copia editable de una Proposal Section (o contenido manual, si `proposal_section` está vacío). Al
	pasar a En Revisión, `docstatus=1` la vuelve inmutable — sin snapshot paralelo ni freeze narrativo.
	"""

	pass
