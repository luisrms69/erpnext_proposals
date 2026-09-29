# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Handoff de compras (mínimo): enriquece la Task **Gestión de Compras** ya materializada por el paquete
``default_procurement_package_item`` con una sección gestionada por la app que documenta, para el PM, qué
compras están previstas según el alcance AUTORIZADO VIGENTE del Project (propuesta raíz + addendas
aplicadas).

Solo documenta (texto): NO crea Material Request / Purchase Order / Purchase Invoice / Supplier Quotation,
NO trae proveedor / warehouse / precio / fechas, NO toca el paquete, el forecast, la economía ni el modelo
de addendas. Identidad por **ocurrencia** (fila origen), nunca dedup por ``item_code``.

Alcance actual: solo ALTAS/adiciones (lo que el modelo de addenda-delta representa hoy). Reducción,
cancelación específica y sustitución de una obligación previa quedan como **gap del modelo de addendas
existente** (no se resuelven aquí).
"""

import frappe
from frappe import _
from frappe.utils import flt

from erpnext_proposals.erpnext_proposals.utils.addendum import resolve_root_group
from erpnext_proposals.erpnext_proposals.utils.project_economics import (
	_applied_addenda,
	_resolve_root_quotation,
)
from erpnext_proposals.erpnext_proposals.utils.quotation import _proposal_settings

# Marcadores de la sección gestionada por la app (idempotencia; preserva el resto de la descripción).
SECTION_START = "<!-- procurement:start -->"
SECTION_END = "<!-- procurement:end -->"


def _package_item(company: str | None) -> str | None:
	"""Item del paquete de Gestión de Compras configurado para la Company (o None)."""
	settings = _proposal_settings(company)
	return settings.get("default_procurement_package_item") if settings else None


def _is_applicable_purchasable(item_code: str | None, package: str | None) -> bool:
	"""Mismas reglas de procurement vigentes: comprable (`is_purchase_item=1`), sin
	`proposal_skip_procurement`, excluyendo el propio paquete. (No dedup: el filtro es por Item; la
	identidad por ocurrencia la aporta la fila.)"""
	if not item_code or item_code == package:
		return False
	it = frappe.db.get_value(
		"Item", item_code, ["is_purchase_item", "proposal_skip_procurement"], as_dict=True
	)
	return bool(it and it.is_purchase_item and not it.get("proposal_skip_procurement"))


def _obligations_for_project(project: str) -> list[dict]:
	"""Reconstruye las obligaciones comprables del alcance AUTORIZADO VIGENTE con el modelo ACTUAL:
	propuesta raíz Ganada + addendas aplicadas (`proposal_project == project`), por **ocurrencia**.

	Reutiliza la MISMA resolución del contrato económico (`_resolve_root_quotation` / `_applied_addenda`),
	que identifica las addendas aplicadas por `proposal_project`. No depende de snapshots económicos (solo
	lee filas de Items/Required). Aditivo: refleja lo que el modelo de addenda-delta representa hoy."""
	root_name = _resolve_root_quotation(project)
	root_group = resolve_root_group(frappe.db.get_value("Quotation", root_name, "proposal_group"))
	proposals = [root_name, *_applied_addenda(project, root_group)]

	obligations: list[dict] = []
	for qname in proposals:
		doc = frappe.get_doc("Quotation", qname)
		package = _package_item(doc.get("company"))
		for it in doc.get("items") or []:
			if _is_applicable_purchasable(it.item_code, package):
				obligations.append(
					{
						"source_type": "sold",
						"source_row": it.name,
						"item_code": it.item_code,
						"item_name": it.get("item_name") or it.item_code,
						"qty": flt(it.get("qty")),
						"uom": it.get("uom") or it.get("stock_uom") or "",
					}
				)
		for ri in doc.get("required_items") or []:
			if _is_applicable_purchasable(ri.item, package):
				obligations.append(
					{
						"source_type": "required",
						"source_row": ri.name,
						"item_code": ri.item,
						"item_name": frappe.db.get_value("Item", ri.item, "item_name") or ri.item,
						"qty": flt(ri.get("qty")) or 1.0,
						"uom": ri.get("uom") or "",
					}
				)
	return obligations


def _procurement_task(project: str) -> str | None:
	"""Localiza la Task de Gestión de Compras de forma ESTRUCTURAL (no por título): la Task del Project
	materializada desde la fila de Scope del paquete (``item_code == default_procurement_package_item``),
	vía la relación existente ``Quotation Scope Item.project_task`` / ``Task.source_quotation_scope_item``.

	Si hay varias (p. ej. el paquete reapareció en una addenda), se elige la canónica determinista (nombre
	mínimo). None si no hay paquete configurado o no se materializó (comportamiento seguro: no-op)."""
	root_name = _resolve_root_quotation(project)
	package = _package_item(frappe.db.get_value("Quotation", root_name, "company"))
	if not package:
		return None
	rows = frappe.get_all(
		"Quotation Scope Item",
		filters={"item_code": package, "project_task": ["!=", ""]},
		pluck="project_task",
	)
	tasks = sorted({t for t in rows if t and frappe.db.get_value("Task", t, "project") == project})
	return tasks[0] if tasks else None


def _render_section(obligations: list[dict]) -> str:
	"""HTML de la sección gestionada. Sin costo/proveedor/fechas. Una línea por OCURRENCIA."""
	if not obligations:
		body = "<p><em>{0}</em></p>".format(_("Sin compras previstas."))
	else:
		items = "".join(
			"<li>{qty:g} × {code} — {name} — {uom}</li>".format(  # noqa: RUF001
				qty=o["qty"],
				code=frappe.utils.escape_html(o["item_code"]),
				name=frappe.utils.escape_html(o["item_name"]),
				uom=frappe.utils.escape_html(o["uom"]) or "—",
			)
			for o in obligations
		)
		body = "<ul>{0}</ul>".format(items)
	heading = "<p><strong>{0}</strong></p>".format(_("Compras previstas"))
	return heading + body


def _upsert_managed_section(description: str | None, section_html: str) -> str:
	"""Inserta o REEMPLAZA solo el bloque entre marcadores, preservando el resto. Idempotente: un segundo
	refresh no duplica la sección."""
	block = "{start}\n{html}\n{end}".format(start=SECTION_START, html=section_html, end=SECTION_END)
	desc = description or ""
	if SECTION_START in desc and SECTION_END in desc:
		pre = desc.split(SECTION_START, 1)[0]
		post = desc.split(SECTION_END, 1)[1]
		return (pre + block + post).strip("\n")
	if not desc.strip():
		return block
	return desc.rstrip("\n") + "\n" + block


def refresh_procurement_task_description(project: str) -> str | None:
	"""Refresca (idempotente) la sección gestionada de Gestión de Compras en la Task del Project. Devuelve
	el nombre de la Task actualizada, o None si no aplica (sin paquete/Task → no-op seguro).

	Se invoca tras materializar el Project (al ganar) y tras aplicar una addenda. NO crea la Task ni altera
	su otra descripción; NO toca economía/forecast/paquete. Escribe solo ``Task.description`` (mismo patrón
	de escritura server-side que el resto de la materialización; sin commit propio)."""
	if not project or not frappe.db.exists("Project", project):
		return None
	task = _procurement_task(project)
	if not task:
		return None
	obligations = _obligations_for_project(project)
	current = frappe.db.get_value("Task", task, "description")
	updated = _upsert_managed_section(current, _render_section(obligations))
	if updated != (current or ""):
		frappe.db.set_value("Task", task, "description", updated, update_modified=False)
	return task
