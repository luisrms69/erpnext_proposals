"""Helpers de Proposal Phase.

`phase` (en Scope Item y Quotation Scope Item) es un Link a Proposal Phase: almacena el
`name` (= `phase_code`). El orden en propuestas/reportes/Tasks usa `Proposal Phase.sequence`
(no el orden alfabético del código) y el display usa `phase_name` legible.

No se duplica `sequence` en los DocTypes: se resuelve desde el catálogo en tiempo de lectura.
"""

import frappe


def phase_label(phase: str) -> str:
	"""Nombre legible (`phase_name`) de una Proposal Phase; fallback al name si falta."""
	if not phase:
		return ""
	return frappe.get_cached_value("Proposal Phase", phase, "phase_name") or phase


def phase_sequence(phase: str) -> int:
	"""`sequence` de la Proposal Phase para ordenar; 0 si no hay fase o no existe."""
	if not phase:
		return 0
	seq = frappe.get_cached_value("Proposal Phase", phase, "sequence")
	return int(seq) if seq is not None else 0


def order_phases(phases: list) -> list:
	"""Ordena una lista de Proposal Phase (`name`) por `sequence`, luego por label."""
	return sorted(phases, key=lambda p: (phase_sequence(p), phase_label(p) or ""))
