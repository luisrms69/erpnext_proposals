# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Integración fiscal de Quotation con ``facturacion_mexico`` (adapter en erpnext_proposals).

Aplica automáticamente el Sales Taxes and Charges Template (STCT) a una Quotation comercial,
reutilizando —**por importación, sin modificarlos**— los helpers de *resolución* de
``facturacion_mexico`` (Customer → Cost Center → Branch → zona → variante → STCT).

``facturacion_mexico`` permanece **100% read-only**: este módulo no altera su código, hooks,
handlers ni el flujo de Sales Invoice; solo importa funciones puras de resolución.

Decisiones de diseño (confirmadas):
- **Suave**: si no se resuelve un STCT, la Quotation se guarda sin bloquear (no ``frappe.throw``).
- **Respeta selección manual**: si ``taxes_and_charges`` ya tiene valor, no se sobrescribe.
- **Sin ITT por línea** en esta versión.
- **Sin ``msgprint``/alertas** en Quotation.

Por eso NO se importa ``_set_stct_by_branch`` (bloquea con ``frappe.throw`` y emite ``msgprint``):
la aplicación final se hace aquí con el nativo de ERPNext ``get_taxes_and_charges``.
"""

import frappe


def apply_fiscal_taxes(doc, method=None):
	"""Hook ``before_validate`` de Quotation: fija ``taxes_and_charges`` + ``taxes`` desde la
	configuración fiscal de ``facturacion_mexico``.

	No intrusivo y a prueba de fallos: cualquier problema de resolución deja la Quotation intacta
	(nunca bloquea el guardado).
	"""
	# Respetar selección manual del usuario.
	if doc.get("taxes_and_charges"):
		return
	# Solo aplica a cotizaciones dirigidas a un Customer (no CRM Deal / Lead / Prospect).
	if doc.get("quotation_to") != "Customer":
		return

	try:
		_resolve_and_apply(doc)
	except Exception:
		# El flujo comercial NUNCA debe bloquearse por la resolución fiscal: se registra y se sigue.
		frappe.logger("erpnext_proposals").warning(
			f"apply_fiscal_taxes: se omite la resolución fiscal para Quotation "
			f"{doc.get('name') or '(nueva)'}: {frappe.get_traceback()}"
		)


def _resolve_and_apply(doc) -> None:
	"""Resuelve el STCT reutilizando los helpers de ``facturacion_mexico`` y lo aplica de forma suave.

	Reutilizados por importación (funciones puras de lectura, sin efectos secundarios):
	``_get_customer_default_cc``, ``_get_branch_from_cost_center``, ``_get_border_zone_status``,
	``_determinar_variante_stct``, ``_find_stct_by_variant``.
	NO se usa ``_set_stct_by_branch`` (comportamiento bloqueante).
	"""
	from facturacion_mexico.hooks_handlers.sales_invoice_automated_tax import (
		_determinar_variante_stct,
		_find_stct_by_variant,
		_get_border_zone_status,
		_get_branch_from_cost_center,
		_get_customer_default_cc,
	)

	# Customer: en Quotation es party_name cuando quotation_to == "Customer".
	customer = doc.get("party_name")

	# Cost Center: el de la propuesta (Custom Field de erpnext_proposals) o el default del Customer.
	cost_center = doc.get("proposal_cost_center") or _get_customer_default_cc(customer)
	if not cost_center:
		return

	# Branch / Oficina Fiscal (mapeo 1:1 desde el Cost Center).
	branch = _get_branch_from_cost_center(cost_center)
	if not branch:
		return

	# Zona fiscal (Nacional/Frontera). Si la sucursal no define zona, no resolvemos.
	is_border = _get_border_zone_status(branch)
	if is_border is None:
		return
	zona = "Frontera" if is_border else "Nacional"

	# Variante por clasificación de items (Básico/IEPS/Retenciones/Total), con fallback a Básico.
	variant = _determinar_variante_stct(doc)
	stct = _find_stct_by_variant(doc.company, zona, variant)
	if not stct and variant != "Básico":
		stct = _find_stct_by_variant(doc.company, zona, "Básico")
	if not stct:
		return

	# Aplicación SUAVE con el nativo de ERPNext (no _set_stct_by_branch).
	from erpnext.controllers.accounts_controller import get_taxes_and_charges

	tax_rows = get_taxes_and_charges("Sales Taxes and Charges Template", stct)
	if not tax_rows:
		return

	doc.taxes_and_charges = stct
	doc.set("taxes", [])
	doc.extend("taxes", tax_rows)
