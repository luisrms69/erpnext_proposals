"""Candado de Print Formats históricos.

Un Print Format se vuelve **histórico** en cuanto una propuesta ya congelada/formalizada lo dejó
guardado en `proposal_effective_print_format` (campo que el app persiste **solo** al congelar
Borrador → En Revisión; nunca en Borrador). Ese campo queda como **referencia/auditoría** de qué
formato se usó.

Modelo definitivo: el histórico oficial de una propuesta congelada son los **PDFs oficiales adjuntos**
generados durante el freeze (protegidos contra borrado, ver `official_document_protection.py`); una
propuesta congelada **no se reimprime** normalmente. Por eso este candado protege el **contenido /
representación** de un Print Format histórico (para que un PDF que sí se regenerara por alguna vía no
saliera distinto) pero **NO** su campo `disabled`: `disabled` no forma parte de la representación
histórica, y deshabilitar un formato sustituido es parte del versionamiento normal (deja de ofrecerse
para nuevas selecciones sin alterar nada del histórico).

Este módulo bloquea, mediante `doc_events` estándar de Frappe (sin tocar core), las operaciones que
alterarían la representación histórica: cambio real de campos de presentación (HTML/CSS/etc.), rename y
delete. **Permite** cambiar `disabled` (típicamente `0 → 1`) aunque el formato sea histórico. La forma
soportada de evolucionar un formato es **crear uno nuevo con otro nombre** y deshabilitar el anterior.
No hay excepción administrativa para lo que sí se bloquea (ni System Manager ni Administrator).

Genérico: no hardcodea nombres de Print Formats. Idempotente con el loader del pack: si se re-guarda
exactamente el mismo contenido de un formato histórico, ningún campo protegido cambia → no se bloquea.
"""

import frappe
from frappe import _

# Campos cuyo cambio altera la REPRESENTACIÓN de un Print Format histórico. Se protegen para que la
# evidencia histórica no pueda mutarse. NO se incluyen metadatos sin efecto sobre la presentación
# (p. ej. `module`, breaks de layout del formulario) ni `disabled`.
#
# `disabled` NO está aquí a propósito (modelo definitivo): no forma parte de la representación
# histórica —el histórico se consulta por los PDFs oficiales adjuntos, no reimprimiendo— y debe poder
# pasar de 0 → 1 al sustituir un formato por una versión nueva, por la vía normal de `doc.save()`.
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
	# ADR-0015: el renderer profile es representación contractual del PDF — cambiarlo en un formato
	# histórico equivale a cambiar cómo se genera ese documento. Se protege igual que HTML/CSS.
	"proposal_renderer_profile",
	"standard",
	"doc_type",
	"print_format_for",
	"report",
)

_EVOLVE_HINT = (
	"Para evolucionar o corregir un formato, crea un Print Format NUEVO con otro nombre, asígnalo a las "
	"propuestas futuras (por ejemplo, en el Proposal Template) y deshabilita el anterior. El CONTENIDO "
	"de un formato ya usado por propuestas formalizadas es inmutable (su histórico se conserva por los "
	"PDFs oficiales adjuntos); sí puede deshabilitarse."
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
		).format(doc.name, ", ".join(changed), _(_EVOLVE_HINT)),
		title=_("Print Format histórico protegido"),
	)


def protect_historical_print_format_on_trash(doc, method=None):
	"""Bloquea la eliminación de un Print Format ya histórico."""
	if is_print_format_historical(doc.name):
		frappe.throw(
			_(
				"El Print Format '{0}' ya es histórico (usado por una o más propuestas formalizadas) y no "
				"puede eliminarse: rompería la reimpresión de esas propuestas. {1}"
			).format(doc.name, _(_EVOLVE_HINT)),
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
			).format(old, _(_EVOLVE_HINT)),
			title=_("Print Format histórico protegido"),
		)
