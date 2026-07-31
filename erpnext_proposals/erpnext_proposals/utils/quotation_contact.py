# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Resolución y persistencia del contacto dirigido de la Quotation (propuesta).

Las Quotations comerciales pueden originarse desde un **CRM Deal** (Frappe CRM) y quedar dirigidas
al **Customer** correspondiente. La propuesta pertenece al Customer, pero está dirigida al **contacto
con quien se lleva el Deal**. Este módulo resuelve y **persiste** ese contacto en la Quotation, dentro
del ciclo normal del documento (sin patches, backfills manuales ni escrituras directas a BD).

Dos puntos, misma resolución (Deal → Customer), distinto grado de autoridad:

- **``before_insert`` (creación):** el contacto del Deal es **autoritativo** — gana aunque el prefill
  del CRM o el fetch nativo hayan puesto otro/nada. Sin contacto del Deal, se hace fallback al contacto
  por defecto del Customer.
- **``validate`` (autocorrección):** solo cuando ``docstatus==0``, ``quotation_to=="Customer"`` y
  ``contact_person`` **vacío**. Rellena (Deal, si no, Customer). Si ya hay ``contact_person``, **no lo
  sobrescribe** (protege una selección manual posterior). Así, un Draft antiguo sin contacto se corrige
  solo al guardarse; no toca Submitted/frozen.

Los derivados (``contact_display``/``contact_email``/``contact_mobile``/...) se pueblan con el nativo
``get_contact_details``. El Print Format sigue usando ``doc.contact_display`` sin lógica especial.
"""

import frappe
from frappe.contacts.doctype.contact.contact import get_contact_details, get_default_contact


def set_proposal_contact(doc, method=None):
	"""Hook ``Quotation.before_insert``: el contacto del Deal es autoritativo en la creación."""
	_apply_directed_contact(doc, authoritative=True)


def autocorrect_missing_contact(doc, method=None):
	"""Hook ``Quotation.validate``: autocorrige Drafts con ``contact_person`` vacío (solo si vacío)."""
	if doc.docstatus != 0:
		return
	_apply_directed_contact(doc, authoritative=False)


def _apply_directed_contact(doc, authoritative: bool) -> None:
	if doc.get("quotation_to") != "Customer" or not doc.get("party_name"):
		return

	deal_contact = _deal_primary_contact(doc.get("crm_deal"))

	if authoritative and deal_contact:
		contact = deal_contact  # el Deal gana en la creación
	else:
		if doc.get("contact_person"):
			return  # ya tiene contacto: no sobrescribir
		contact = deal_contact or get_default_contact("Customer", doc.party_name)

	if not contact:
		return

	doc.contact_person = contact
	_apply_contact_details(doc, contact)


def _deal_primary_contact(crm_deal: str | None) -> str | None:
	"""Contact primario del CRM Deal, o el primero disponible. Guardado si el app ``crm`` no está.

	No acopla por import al app ``crm``: lee por ``frappe.db`` y solo si el DocType existe.
	"""
	if (
		not crm_deal
		or not frappe.db.exists("DocType", "CRM Deal")
		or not frappe.db.exists("CRM Deal", crm_deal)
	):
		return None

	primary = frappe.get_all(
		"CRM Contacts",
		filters={"parent": crm_deal, "parenttype": "CRM Deal", "is_primary": 1},
		pluck="contact",
		order_by="idx asc",
		limit=1,
	)
	candidate = primary[0] if primary else None
	if not candidate:
		candidate = frappe.db.get_value("CRM Deal", crm_deal, "contact")
	if not candidate:
		any_row = frappe.get_all(
			"CRM Contacts",
			filters={"parent": crm_deal, "parenttype": "CRM Deal"},
			pluck="contact",
			order_by="idx asc",
			limit=1,
		)
		candidate = any_row[0] if any_row else None

	return candidate if (candidate and frappe.db.exists("Contact", candidate)) else None


def _apply_contact_details(doc, contact: str) -> None:
	"""Puebla ``contact_display``/``contact_email``/``contact_mobile``/... desde el contacto dado.

	Reutiliza el nativo ``get_contact_details`` (no cambia qué contacto es). Solo asigna los campos
	que existan en Quotation.
	"""
	for field, value in get_contact_details(contact).items():
		if doc.meta.has_field(field):
			doc.set(field, value)
