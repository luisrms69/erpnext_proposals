"""Candado de Print Formats históricos.

Un Print Format se vuelve **histórico** en cuanto una propuesta ya congelada/formalizada lo dejó
guardado en `proposal_effective_print_format` (campo que el app persiste **solo** al congelar
Borrador → En Revisión; nunca en Borrador). A partir de ese momento, reimprimir una propuesta
histórica usa el HTML **actual** de ese Print Format, así que modificarlo/renombrarlo/eliminarlo
cambiaría retrospectivamente la presentación de propuestas ya emitidas.

Este módulo bloquea, mediante `doc_events` estándar de Frappe (sin tocar core), las operaciones que
alterarían esa reimpresión histórica: cambio real de campos de presentación, `disabled`, rename y
delete. La forma soportada de evolucionar un formato es **crear uno nuevo con otro nombre** y usarlo
solo en propuestas futuras. No hay excepción administrativa (ni System Manager ni Administrator).

Genérico: no hardcodea nombres de Print Formats. Idempotente con el loader del pack: si se re-guarda
exactamente el mismo contenido de un formato histórico, ningún campo protegido cambia → no se bloquea.
"""

import frappe
from frappe import _

# Campos cuyo cambio altera la representación reimpresa de un Print Format (o rompe la reimpresión).
# NO se incluyen metadatos sin efecto sobre la presentación histórica (p. ej. `module`, ayudas HTML,
# breaks de layout del formulario).
_PRESENTATION_FIELDS = (
	"html",
	"css",
	"format_data",
	"print_format_type",
	"custom_format",
	"raw_printing",
	"raw_commands",
	"print_format_builder",
	"absolute_value",
	"align_labels_right",
	"show_section_headings",
	"line_breaks",
	"default_print_language",
	"font",
	"font_size",
	"margin_top",
	"margin_bottom",
	"margin_left",
	"margin_right",
	"page_number",
	"pdf_generator",
	"standard",
	"doc_type",
	"print_format_for",
	"report",
	# `disabled`: deshabilitar un formato histórico rompe su reimpresión (el resolver rechaza formatos
	# deshabilitados). Se bloquea cualquier cambio de este campo en un formato histórico.
	"disabled",
)

_EVOLVE_HINT = _(
	"Para evolucionar o corregir un formato, crea un Print Format NUEVO con otro nombre y asígnalo a "
	"las propuestas futuras (por ejemplo, en el Proposal Template). Los formatos ya usados por "
	"propuestas formalizadas son inmutables para preservar su reimpresión."
)


def is_print_format_historical(name: str | None) -> bool:
	"""True si alguna propuesta congelada/formalizada dejó este Print Format como su formato efectivo.

	`Quotation.proposal_effective_print_format` se persiste únicamente al congelar (Borrador → En
	Revisión); su presencia con este nombre == el formato ya es histórico.
	"""
	if not name:
		return False
	return bool(frappe.db.exists("Quotation", {"proposal_effective_print_format": name}))


def protect_historical_print_format_on_save(doc, method=None):
	"""Bloquea cambios de presentación (o `disabled`) sobre un Print Format ya histórico.

	Idempotente: si ningún campo protegido cambió (p. ej. el loader re-aplicando el mismo contenido),
	no bloquea. En un documento nuevo no aplica (aún no puede ser histórico).
	"""
	if doc.get("__islocal") or doc.is_new():
		return
	if not is_print_format_historical(doc.name):
		return
	changed = [f for f in _PRESENTATION_FIELDS if doc.has_value_changed(f)]
	if not changed:
		return
	frappe.throw(
		_(
			"El Print Format '{0}' ya es histórico (usado por una o más propuestas formalizadas) y no "
			"puede modificarse: cambiaría retrospectivamente la presentación de esas propuestas. "
			"Campos bloqueados en este intento: {1}. {2}"
		).format(doc.name, ", ".join(changed), _EVOLVE_HINT),
		title=_("Print Format histórico protegido"),
	)


def protect_historical_print_format_on_trash(doc, method=None):
	"""Bloquea la eliminación de un Print Format ya histórico."""
	if is_print_format_historical(doc.name):
		frappe.throw(
			_(
				"El Print Format '{0}' ya es histórico (usado por una o más propuestas formalizadas) y no "
				"puede eliminarse: rompería la reimpresión de esas propuestas. {1}"
			).format(doc.name, _EVOLVE_HINT),
			title=_("Print Format histórico protegido"),
		)


def protect_historical_print_format_on_rename(doc, method=None, old=None, new=None, merge=False):
	"""Bloquea el rename de un Print Format ya histórico (las propuestas apuntan a él por NOMBRE)."""
	if is_print_format_historical(old):
		frappe.throw(
			_(
				"El Print Format '{0}' ya es histórico (usado por una o más propuestas formalizadas) y no "
				"puede renombrarse: las propuestas lo referencian por nombre y su reimpresión fallaría. "
				"{1}"
			).format(old, _EVOLVE_HINT),
			title=_("Print Format histórico protegido"),
		)
