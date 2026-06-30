# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ProposalPhase(Document):
	"""Catálogo único de fases de propuesta.

	`phase_code` es el identificador estable e inmutable de la fase. La inmutabilidad
	se garantiza con tres capas:
	  1. `autoname = field:phase_code` + `set_only_once` (capa declarativa).
	  2. `validate` → `_enforce_immutable_code` (guard explícito contra el valor en BD;
	     `set_only_once` por sí solo no siempre bloquea cuando el campo es el autoname).
	  3. `before_rename` + `allow_rename = 0` (bloquea el rename del documento).

	`phase_name`, `sequence` y `enabled` sí son editables; las propuestas históricas
	conservan su propio snapshot de la fase, por lo que cambiar el nombre o la secuencia
	aquí no altera documentos ya generados.

	Nota: estos guards protegen la capa de documento (save/rename). Un
	`frappe.db.set_value` crudo es un bypass de bajo nivel deliberado del framework y
	queda fuera de alcance, igual que para cualquier otro campo.
	"""

	def validate(self):
		self._enforce_immutable_code()

	def _enforce_immutable_code(self):
		if self.is_new():
			return
		old_code = frappe.db.get_value("Proposal Phase", self.name, "phase_code")
		if old_code is not None and self.phase_code != old_code:
			frappe.throw(
				_("El código de fase (phase_code) es inmutable y no puede cambiarse."),
				frappe.exceptions.CannotChangeConstantError,
				title=_("Operación no permitida"),
			)

	def before_rename(self, old_name, new_name, merge=False):
		frappe.throw(
			_("El código de fase (phase_code) es inmutable; una Proposal Phase no se puede renombrar."),
			title=_("Operación no permitida"),
		)
