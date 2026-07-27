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


def validate_print_format(pf_name: str | None) -> None:
	"""Valida que un Print Format sea usable para Quotation. Error claro si no (Caso F)."""
	if not pf_name:
		return
	pf = frappe.db.get_value("Print Format", pf_name, ["doc_type", "disabled"], as_dict=True)
	if not pf:
		frappe.throw(_("El Print Format '{0}' no existe.").format(pf_name))
	if pf.doc_type != "Quotation":
		frappe.throw(
			_("El Print Format '{0}' pertenece a '{1}', no a Quotation.").format(pf_name, pf.doc_type)
		)
	if pf.disabled:
		frappe.throw(_("El Print Format '{0}' está deshabilitado.").format(pf_name))


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
