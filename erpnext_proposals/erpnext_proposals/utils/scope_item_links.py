# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Relación Item ↔ Scope Item + resolver central (fuente única de verdad).

Modelo vigente: child table `Scope Item.erpnext_items` (DocType `Scope Item ERPNext Item`, N:N).
Compatibilidad de transición: `Scope Item.erpnext_item` (un solo Item) sigue siendo válido en LECTURA.
No hay migración masiva: `resolve_scope_items_for_item` une ambas fuentes y deduplica, de modo que las
relaciones legacy y las nuevas funcionen indistintamente sin backfill ni patch."""

import frappe
from frappe import _


def _scope_items_from_child(item: str) -> list[str]:
	"""Scope Items (== code) cuya child table `erpnext_items` incluye `item`."""
	return frappe.get_all(
		"Scope Item ERPNext Item",
		filters={"item": item, "parenttype": "Scope Item", "parentfield": "erpnext_items"},
		pluck="parent",
	)


def _scope_items_from_legacy(item: str) -> list[str]:
	"""Scope Items cuyo Link legacy `erpnext_item` es `item`."""
	return frappe.get_all("Scope Item", filters={"erpnext_item": item}, pluck="name")


def resolve_scope_items_for_item(item: str, enabled_only: bool = False) -> list[str]:
	"""FUENTE ÚNICA Item → Scope Items. Une la child table N:N y el Link legacy, deduplica y
	(opcionalmente) filtra `enabled=1`. Todo el app debe resolver la relación por aquí — no repetir
	consultas N:N/legacy en otros archivos."""
	names = set(_scope_items_from_child(item)) | set(_scope_items_from_legacy(item))
	if not names:
		return []
	if enabled_only:
		names = set(
			frappe.get_all("Scope Item", filters={"name": ["in", list(names)], "enabled": 1}, pluck="name")
		)
	return sorted(names)


@frappe.whitelist()
def get_scope_items_for_item(item: str) -> list[dict]:
	"""Scope Items asociados a un Item (child + legacy) para el diálogo desde el formulario Item."""
	frappe.has_permission("Item", "read", doc=item, throw=True)
	names = resolve_scope_items_for_item(item)
	if not names:
		return []
	return frappe.get_all(
		"Scope Item",
		filters={"name": ["in", names]},
		fields=["name", "code", "title", "enabled"],
		order_by="code asc",
	)


@frappe.whitelist()
def set_scope_items_for_item(item: str, scope_items: str | list) -> dict:
	"""Guarda la selección de Scope Items para UN Item (edición explícita del usuario, no migración):

	- agrega `item` a la child table de los Scope Items recién seleccionados que no lo tengan;
	- en los deseleccionados: quita SOLO la fila child de ESE Item y, si el Link legacy `erpnext_item`
	  del Scope Item es exactamente ese Item, lo limpia;
	- nunca toca las relaciones de esos Scope Items con otros Items;
	- no duplica; solo permite AGREGAR Scope Items habilitados.
	"""
	if not frappe.has_permission("Scope Item", "write"):
		frappe.throw(_("No está autorizado para modificar Scope Items."), frappe.PermissionError)
	if not frappe.db.exists("Item", item):
		frappe.throw(_("El Item '{0}' no existe.").format(item))

	selected = set(frappe.parse_json(scope_items) or [])
	current = set(resolve_scope_items_for_item(item))
	to_add = selected - current
	to_remove = current - selected

	for code in to_add:
		if not frappe.db.exists("Scope Item", code):
			frappe.throw(_("El Scope Item '{0}' no existe.").format(code))
		if not frappe.db.get_value("Scope Item", code, "enabled"):
			frappe.throw(_("El Scope Item '{0}' está deshabilitado y no puede asociarse.").format(code))

	added = 0
	removed = 0
	for code in to_add:
		doc = frappe.get_doc("Scope Item", code)
		if not any(r.item == item for r in (doc.erpnext_items or [])):
			doc.append("erpnext_items", {"item": item})
			doc.save()
			added += 1
	for code in to_remove:
		doc = frappe.get_doc("Scope Item", code)
		changed = False
		for r in [r for r in (doc.erpnext_items or []) if r.item == item]:
			doc.remove(r)
			changed = True
		if doc.erpnext_item == item:
			doc.erpnext_item = None  # limpia SOLO si el legacy apuntaba exactamente a este Item
			changed = True
		if changed:
			doc.save()
			removed += 1

	return {"added": added, "removed": removed}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def scope_package_query(
	doctype: str,
	txt: str,
	searchfield: str,
	start: int,
	page_len: int,
	filters: dict | None,
) -> list[tuple]:
	"""Link-query del picker "Agregar paquete de alcance" (issue #55). Un **paquete de alcance** es un Item
	organizativo —no vendible, no comprable— que agrupa Scope Items por la relación N:M y se incorpora a la
	propuesta como Required Item. Filtro **solo de UX** (no es validación de backend): Items con
	``is_sales_item=0 AND is_purchase_item=0 AND disabled=0`` que tengan **al menos un Scope Item habilitado**
	(child `erpnext_items` + legacy `erpnext_item`). Devuelve ``[(name, item_name)]``."""
	like = f"%{txt}%"
	return frappe.db.sql(
		"""
		SELECT i.name, i.item_name
		FROM `tabItem` i
		WHERE i.is_sales_item = 0 AND i.is_purchase_item = 0 AND i.disabled = 0
		  AND (i.name LIKE %(txt)s OR i.item_name LIKE %(txt)s)
		  AND i.name IN (
			SELECT sie.item
			FROM `tabScope Item ERPNext Item` sie
			INNER JOIN `tabScope Item` si ON si.name = sie.parent
			WHERE si.enabled = 1 AND sie.parentfield = 'erpnext_items'
			UNION
			SELECT si2.erpnext_item
			FROM `tabScope Item` si2
			WHERE si2.enabled = 1 AND si2.erpnext_item IS NOT NULL AND si2.erpnext_item != ''
		  )
		ORDER BY i.item_name ASC
		LIMIT %(start)s, %(page_len)s
		""",
		{"txt": like, "start": start, "page_len": page_len},
	)


@frappe.whitelist()
def get_scope_package_scope_items(item: str) -> list[dict]:
	"""Preview (code + title) de los Scope Items habilitados de un Item-paquete, para el diálogo de #55.
	Reusa la FUENTE ÚNICA ``resolve_scope_items_for_item``; solo lectura, sin materializar nada."""
	frappe.has_permission("Item", "read", doc=item, throw=True)
	names = resolve_scope_items_for_item(item, enabled_only=True)
	if not names:
		return []
	return frappe.get_all(
		"Scope Item",
		filters={"name": ["in", names]},
		fields=["code", "title"],
		order_by="sequence asc, code asc",
	)
