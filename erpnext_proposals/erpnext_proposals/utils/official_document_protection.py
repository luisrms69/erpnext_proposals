"""Protección contra eliminación accidental de los documentos oficiales de una propuesta.

Los PDFs oficiales que el flujo de propuestas genera y adjunta (propuesta comercial y Rentabilidad
Estimada) quedan marcados de forma inequívoca con el Custom Field `File.is_proposal_official_document`
(lo fija exclusivamente `attach_proposal_pdfs` / `_attach_pdf`; el campo es read_only y no depende del
nombre del archivo). Un File así marcado no puede eliminarse por el flujo normal —ni por usuarios
ordinarios ni por System Manager—: solo `Administrator` (usuario) puede hacerlo deliberadamente, y el
propio flujo interno de regeneración, que reemplaza la versión previa, se exime mediante un flag
explícito.

Genérico y extensible: cualquier File que el flujo marque como oficial queda protegido, sin hardcodear
los nombres de los dos PDFs actuales. No toca permisos generales de `File` ni otros adjuntos. Bloquea
solo la ELIMINACIÓN (`on_trash`), no la lectura/descarga. La condición de oficial vive en el File y NO
depende del `docstatus` de la Quotation: tras cancelar la propuesta, el documento sigue protegido.
"""

import frappe
from frappe import _

# Flag que SOLO activa el flujo interno de generación (attach_proposal_pdfs) mientras reemplaza la
# versión previa de un documento oficial. Es la única vía de exención además de Administrator. No es un
# mecanismo general para saltarse la protección: lo pone y lo quita el propio flujo autorizado.
INTERNAL_REPLACE_FLAG = "in_proposal_official_pdf_generation"

# Campo marcador (Custom Field en File).
OFFICIAL_FLAG_FIELD = "is_proposal_official_document"


def protect_official_document_on_trash(doc, method=None):
	"""Bloquea el borrado de un File marcado como documento oficial de propuesta.

	Excepciones (mínimas y explícitas):
	- `Administrator` (usuario) puede eliminarlo deliberadamente.
	- El flujo interno de regeneración, señalado por `frappe.flags[INTERNAL_REPLACE_FLAG]`.
	"""
	if not doc.get(OFFICIAL_FLAG_FIELD):
		return
	if frappe.flags.get(INTERNAL_REPLACE_FLAG):
		return
	if frappe.session.user == "Administrator":
		return
	frappe.throw(
		_(
			"El archivo '{0}' es un documento oficial de la propuesta y no puede eliminarse. "
			"Es evidencia formal de la propuesta emitida; si necesitas reemplazarlo, usa el flujo del "
			"módulo de propuestas."
		).format(doc.file_name or doc.name),
		title=_("Documento oficial protegido"),
	)
