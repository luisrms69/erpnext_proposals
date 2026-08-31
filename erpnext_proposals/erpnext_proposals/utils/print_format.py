"""Resolución y congelamiento del Print Format comercial de una propuesta (Quotation).

Modelo de resolución (rutas de impresión y de snapshot usan el MISMO resolver):

    Propuesta congelada  → proposal_effective_print_format (inmutable)
    Propuesta en Borrador → proposal_print_format → Proposal Template.print_format → DEFAULT

`proposal_effective_print_format` solo se persiste al congelar (Borrador → En Revisión). En Borrador el
formato efectivo se resuelve dinámicamente y no se graba. `Rentabilidad Estimada` es independiente.
"""

import frappe
from frappe import _

DEFAULT_COMMERCIAL_PRINT_FORMAT = "Propuesta Comercial"

# Criterio ÚNICO de elegibilidad de un Print Format para propuestas. Si mañana se agrega otra regla,
# se cambia AQUÍ y lo heredan por igual: la query del campo Link, la validación de servidor y el
# `status` que consume el warning del cliente. NO duplicar el criterio en otro sitio.
PROPOSAL_PRINT_FORMAT_DOCTYPE = "Quotation"


def _proposal_print_format_filters() -> dict:
	"""Filtros de elegibilidad (fuente única): solo Quotation y no deshabilitado."""
	return {"doc_type": PROPOSAL_PRINT_FORMAT_DOCTYPE, "disabled": 0}


def resolve_commercial_print_format(doc) -> str:
	"""Formato comercial efectivo. Congelada → el congelado; Borrador → resolución dinámica."""
	frozen = doc.get("proposal_effective_print_format")
	if frozen:
		return frozen
	return dynamic_commercial_print_format(doc)


def dynamic_commercial_print_format(doc) -> str:
	"""Resolución dinámica (Borrador): override → Proposal Template → default."""
	pf = doc.get("proposal_print_format")
	if not pf and doc.get("proposal_template"):
		pf = frappe.db.get_value("Proposal Template", doc.proposal_template, "print_format")
	return pf or DEFAULT_COMMERCIAL_PRINT_FORMAT


def sync_proposal_print_format_from_template(doc) -> None:
	"""Puebla el override editable `proposal_print_format` con el Print Format configurado en la
	Proposal Template, de forma GENÉRICA (sin nombres hardcodeados):

	- Solo aplica a Quotations con `proposal_template` (las que no usan plantilla no se tocan).
	- Se puebla cuando se APLICA/CAMBIA la plantilla (`has_value_changed`) o cuando el override está
	  vacío. Así el campo deja de verse vacío y refleja el formato de la plantilla.
	- NO sobrescribe una selección MANUAL del usuario mientras la plantilla no cambie.
	"""
	if not doc.get("proposal_template"):
		return
	template_pf = frappe.db.get_value("Proposal Template", doc.proposal_template, "print_format")
	if not template_pf:
		return
	if doc.has_value_changed("proposal_template") or not doc.get("proposal_print_format"):
		doc.proposal_print_format = template_pf


def _uses_separate_cover(doc, print_format: str) -> bool:
	"""True si el PDF debe generarse con portada separada (2 renders + merge): la Proposal Template
	del documento tiene ``separate_cover_page`` Y el Print Format solicitado es el comercial efectivo
	(no la Rentabilidad ni otros). GENÉRICO: depende solo de metadata de la plantilla, sin nombres
	de documento/cliente/template hardcodeados."""
	tmpl_name = doc.get("proposal_template")
	if not tmpl_name:
		return False
	if not int(frappe.db.get_value("Proposal Template", tmpl_name, "separate_cover_page") or 0):
		return False
	return print_format == resolve_commercial_print_format(doc)


def render_proposal_pdf(doc, print_format: str) -> bytes:
	"""Genera el PDF de una propuesta.

	Si la Proposal Template está marcada con ``separate_cover_page`` y se renderiza su Print Format
	comercial, produce el PDF en DOS renders unidos con el merger PDF nativo de Frappe (sin rasterizar,
	sin postproceso externo):

	- **Render 1 — portada:** ``doc.proposal_render_part='cover'`` + ``no_letterhead`` → solo la portada
	  full-bleed, sin header interior, 1 página.
	- **Render 2 — cuerpo:** ``doc.proposal_render_part='body'`` → todo el cuerpo con el header del
	  Letter Head repetido en TODAS las páginas + footer.

	En cualquier otro caso (plantilla sin la marca, u otro Print Format como Rentabilidad), un solo
	render con el comportamiento estándar. NO monkey-patchea ``get_pdf`` ni afecta otros Print Formats:
	el modo de render se pasa por un atributo del propio ``doc`` que solo este Print Format consume.

	**Renderer profile (ADR-0015):** si el Print Format declara ``gotenberg-v1`` en su renderer profile,
	el render se delega a Gotenberg (motor desacoplado y versionado). Cualquier otro valor (incluido el
	campo ausente/vacío) sigue exactamente por el camino wkhtmltopdf de abajo — compat hacia atrás."""
	from erpnext_proposals.erpnext_proposals.utils.renderer import (
		GOTENBERG_V1,
		get_renderer_profile,
		render_proposal_pdf_gotenberg,
	)

	if get_renderer_profile(print_format) == GOTENBERG_V1:
		return render_proposal_pdf_gotenberg(doc, print_format)

	from frappe.utils.pdf import get_file_data_from_writer, get_pdf

	if not _uses_separate_cover(doc, print_format):
		return get_pdf(frappe.get_print(doc.doctype, doc.name, print_format=print_format))

	import io

	from pypdf import PdfReader, PdfWriter

	writer = PdfWriter()
	try:
		# RENDER 1 — portada. Es por diseño UNA sola página; se toma SOLO la primera del render para
		# garantizar "portada = 1 página" de forma determinista (el min-height de la portada puede rozar
		# el área útil y generar una 2ª página en blanco, que aquí se descarta con el merger nativo).
		doc.proposal_render_part = "cover"
		cover_html = frappe.get_print(
			doc.doctype, doc.name, print_format=print_format, doc=doc, no_letterhead=1
		)
		cover_reader = PdfReader(io.BytesIO(get_pdf(cover_html)))
		writer.add_page(cover_reader.pages[0])

		# RENDER 2 — cuerpo con header (Letter Head) repetido en TODAS sus páginas.
		doc.proposal_render_part = "body"
		body_html = frappe.get_print(doc.doctype, doc.name, print_format=print_format, doc=doc)
		get_pdf(body_html, output=writer)
	finally:
		doc.proposal_render_part = None

	return get_file_data_from_writer(writer)


def sync_letter_head_from_template(doc) -> None:
	"""Puebla el campo NATIVO `letter_head` de la Quotation con el Letter Head configurado en la
	Proposal Template, de forma GENÉRICA (sin nombres hardcodeados):

	- Solo aplica a Quotations con `proposal_template` que además define `letter_head` (si la plantilla
	  no lo define, no se toca: comportamiento nativo de Frappe / default de Company).
	- Se puebla cuando se APLICA/CAMBIA la plantilla (`has_value_changed`) o cuando el campo está vacío.
	  Esto hace que el Letter Head dedicado GANE incluso si erpnext ya pre-rellenó el default de Company
	  en `set_default_letter_head` (accounts_controller), garantizando selección explícita por nombre.
	- NO sobrescribe una selección MANUAL del usuario mientras la plantilla no cambie.
	"""
	if not doc.get("proposal_template"):
		return
	template_lh = frappe.db.get_value("Proposal Template", doc.proposal_template, "letter_head")
	if not template_lh:
		return
	if doc.has_value_changed("proposal_template") or not doc.get("letter_head"):
		doc.letter_head = template_lh


def validate_print_format(pf_name: str | None) -> None:
	"""Valida que un Print Format sea usable para Quotation (elegibilidad única). Error claro si no."""
	if not pf_name:
		return
	pf = frappe.db.get_value("Print Format", pf_name, ["doc_type", "disabled"], as_dict=True)
	if not pf:
		frappe.throw(_("El Print Format '{0}' no existe.").format(pf_name))
	if pf.doc_type != PROPOSAL_PRINT_FORMAT_DOCTYPE:
		frappe.throw(
			_("El Print Format '{0}' pertenece a '{1}', no a Quotation.").format(pf_name, pf.doc_type)
		)
	if pf.disabled:
		frappe.throw(_("El Print Format '{0}' está deshabilitado.").format(pf_name))


def assert_assignable_print_format(doc, fieldname: str) -> None:
	"""Validación de servidor COMPARTIDA (Quotation.proposal_print_format y Proposal Template.print_format).

	Impide que un documento **nuevo o editable** *adopte* (asigne/cambie a) un Print Format no elegible
	(inexistente / de otro DocType / deshabilitado). Protege lo histórico: si el valor NO cambió respecto
	a lo ya guardado, no se re-valida — así un documento congelado o una plantilla existente que ya
	referencian un formato **posteriormente deshabilitado** conservan su referencia sin invalidarse
	retroactivamente. No relaja ADR-0011 (candado de formatos históricos): es una capa distinta.
	"""
	value = doc.get(fieldname)
	if not value:
		return
	# Solo validar cuando el valor se ADOPTA: documento nuevo, o el campo cambió respecto a BD.
	if not doc.is_new() and not doc.has_value_changed(fieldname):
		return
	validate_print_format(value)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_proposal_print_formats(
	doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: dict
) -> list:
	"""Query central del campo Link para elegir el Print Format de una propuesta.

	Fuente ÚNICA de elegibilidad (``_proposal_print_format_filters``): solo ``doc_type='Quotation'`` y
	``disabled=0``. La usan por igual ``Quotation.proposal_print_format`` y ``Proposal Template.print_format``
	(vía ``set_query`` en el cliente). Soporta la búsqueda estándar de Frappe sobre el nombre.
	"""
	return frappe.get_all(
		"Print Format",
		filters={**_proposal_print_format_filters(), "name": ["like", f"%{txt}%"]},
		fields=["name"],
		limit_start=start,
		limit=page_len,
		order_by="modified desc",
		as_list=True,
	)


@frappe.whitelist()
def get_print_format_status(pf_name: str | None) -> dict:
	"""Estado de elegibilidad de un Print Format referenciado (para el warning del cliente).

	Devuelve ``{"status": ok|missing|disabled|wrong_doctype}`` usando el MISMO criterio que la query y
	la validación. Lectura ligera (un solo ``get_value``); el cliente la invoca una vez al cargar.
	"""
	if not pf_name:
		return {"status": "ok"}
	pf = frappe.db.get_value("Print Format", pf_name, ["doc_type", "disabled"], as_dict=True)
	if not pf:
		return {"status": "missing"}
	if pf.doc_type != PROPOSAL_PRINT_FORMAT_DOCTYPE:
		return {"status": "wrong_doctype", "doc_type": pf.doc_type}
	if pf.disabled:
		return {"status": "disabled"}
	return {"status": "ok"}


def freeze_effective_print_format(doc) -> None:
	"""Persiste el formato comercial efectivo al congelar. Idempotente (no re-congela)."""
	if not doc.get("proposal_effective_print_format"):
		doc.proposal_effective_print_format = dynamic_commercial_print_format(doc)


@frappe.whitelist()
def get_effective_commercial_print_format(quotation: str) -> str:
	"""Formato comercial efectivo de una Quotation (usado por el botón de impresión en JS)."""
	doc = frappe.get_doc("Quotation", quotation)
	doc.check_permission("read")
	return resolve_commercial_print_format(doc)


@frappe.whitelist()
def download_commercial_draft_pdf(quotation: str) -> None:
	"""Descarga un PDF **BORRADOR** (no oficial) de la Propuesta Comercial, para revisión externa
	mientras la Quotation sigue editable.

	Resuelve el Print Format efectivo con ``resolve_commercial_print_format`` y genera los bytes
	EXCLUSIVAMENTE con ``render_proposal_pdf`` — única puerta al renderer, que despacha a Gotenberg o al
	camino legacy wkhtmltopdf según el renderer profile del Print Format (ADR-0015).

	Es solo una descarga de conveniencia: **NO** adjunta el PDF ni crea File oficial, **NO** congela
	(``proposal_effective_print_format``/secciones/tarifas/snapshot), **NO** cambia ``workflow_state``,
	**NO** hace submit y **NO** invoca ``attach_proposal_pdfs``. El documento formal se genera aparte al
	pasar a *En Revisión* (flujo intacto). El ``filename`` lleva el prefijo ``BORRADOR`` para que nunca se
	confunda con el documento oficial.
	"""
	doc = frappe.get_doc("Quotation", quotation)
	doc.check_permission("read")

	print_format = resolve_commercial_print_format(doc)
	pdf_bytes = render_proposal_pdf(doc, print_format)

	frappe.local.response.filename = f"BORRADOR - Propuesta Comercial - {doc.name}.pdf"
	frappe.local.response.filecontent = pdf_bytes
	frappe.local.response.content_type = "application/pdf"
	frappe.local.response.type = "download"
