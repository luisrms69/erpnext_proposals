import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	quotation_name = filters.get("quotation")

	if not quotation_name:
		frappe.throw(_("Selecciona una Cotización para generar el reporte."))

	quotation = frappe.get_doc("Quotation", quotation_name)
	currency = quotation.currency or "MXN"
	company_currency = (
		frappe.db.get_value("Company", quotation.company, "default_currency") if quotation.company else None
	)

	columns = _get_columns()
	data = []
	warnings = []

	# Currency warning
	if company_currency and quotation.currency != company_currency:
		warnings.append(
			_(
				"Moneda de Quotation ({0}) ≠ moneda base de Company ({1}) — "
				"comparación de rentabilidad no confiable."
			).format(quotation.currency, company_currency)
		)

	# Items that have Scope Items → cost from hours, not from purchase price
	items_with_scope = {
		row.item_code for row in quotation.quotation_scope_items if row.include_in_proposal and row.item_code
	}

	# ── SECCIÓN 1: Costo laboral (horas) ────────────────────────────────
	data.append(_section(_("COSTO LABORAL (Horas estimadas)")))

	scope_rows = sorted(
		[r for r in quotation.quotation_scope_items if r.include_in_proposal],
		key=lambda r: (r.phase or "", r.sequence or 0, r.idx),
	)

	total_labor_hours = 0.0
	total_labor_cost = 0.0
	missing_activity = 0
	missing_rate = 0
	current_phase = None

	for row in scope_rows:
		if row.phase != current_phase:
			current_phase = row.phase
			if current_phase:
				data.append(_phase_header(current_phase))

		costing_rate = 0.0
		notes = ""
		if not row.activity_type:
			missing_activity += 1
			notes = _("⚠ Sin activity_type")
		else:
			costing_rate = flt(frappe.db.get_value("Activity Type", row.activity_type, "costing_rate") or 0)
			if not costing_rate:
				missing_rate += 1
				notes = _("⚠ Sin costing_rate")

		hours = flt(row.estimated_hours or 0)
		cost = flt(hours * costing_rate)
		total_labor_hours += hours
		total_labor_cost += cost

		data.append(
			{
				"label": row.title or row.code,
				"activity_type": row.activity_type,
				"designation": row.designation,
				"estimated_hours": hours or None,
				"costing_rate": costing_rate or None,
				"estimated_cost": cost or None,
				"notes": notes,
				"currency": currency,
				"indent": 2,
			}
		)

	data.append(
		{
			"label": _("Total costo laboral"),
			"estimated_hours": total_labor_hours,
			"estimated_cost": total_labor_cost,
			"currency": currency,
			"bold": 1,
			"indent": 1,
		}
	)

	# ── SECCIÓN 2: Items comprados / revendidos ──────────────────────────
	data.append(_spacer())
	data.append(_section(_("ITEMS COMPRADOS / REVENDIDOS")))

	total_item_cost = 0.0
	items_without_cost = []

	for item in quotation.items:
		# Skip items already costed by Scope Items
		if item.item_code in items_with_scope:
			data.append(
				{
					"label": item.item_name,
					"notes": _("Costo cubierto por horas (Scope Items)"),
					"currency": currency,
					"indent": 1,
				}
			)
			continue

		cost_per_unit, source = _get_item_cost(item.item_code)
		qty = flt(item.qty)

		if cost_per_unit is None:
			items_without_cost.append(item.item_name)
			data.append(
				{
					"label": item.item_name,
					"notes": _("⚠ Sin costo estimable"),
					"currency": currency,
					"indent": 1,
				}
			)
			continue

		item_total_cost = flt(qty * cost_per_unit)
		total_item_cost += item_total_cost

		data.append(
			{
				"label": item.item_name,
				"costing_rate": cost_per_unit,
				"estimated_cost": item_total_cost,
				"notes": _("Fuente: {0} | Cant: {1}").format(source, flt(qty, 2)),
				"currency": currency,
				"indent": 1,
			}
		)

	data.append(
		{
			"label": _("Total costo items"),
			"estimated_cost": total_item_cost,
			"currency": currency,
			"bold": 1,
			"indent": 1,
		}
	)

	# ── SECCIÓN 3: Venta (Quotation Items) ───────────────────────────────
	data.append(_spacer())
	data.append(_section(_("VENTA (Quotation Items)")))

	for item in quotation.items:
		data.append(
			{
				"label": item.item_name,
				"notes": _("Cant: {0} x {1}").format(
					flt(item.qty, 2), frappe.format_value(item.rate, {"fieldtype": "Currency"})
				),
				"estimated_cost": flt(item.net_amount),
				"currency": currency,
				"indent": 1,
			}
		)

	data.append(
		{
			"label": _("Venta neta"),
			"estimated_cost": flt(quotation.net_total),
			"currency": currency,
			"bold": 1,
			"indent": 1,
		}
	)
	data.append(
		{
			"label": _("Impuestos (informativo)"),
			"estimated_cost": flt(quotation.total_taxes_and_charges),
			"notes": _("Solo informativo"),
			"currency": currency,
			"indent": 1,
		}
	)
	data.append(
		{
			"label": _("Total con impuestos (informativo)"),
			"estimated_cost": flt(quotation.grand_total),
			"notes": _("Solo informativo"),
			"currency": currency,
			"indent": 1,
		}
	)

	# ── SECCIÓN 4: Rentabilidad estimada ─────────────────────────────────
	data.append(_spacer())
	data.append(_section(_("RENTABILIDAD ESTIMADA")))

	net_total = flt(quotation.net_total)
	total_cost = total_labor_cost + total_item_cost
	margin = net_total - total_cost
	margin_pct = (margin / net_total * 100) if net_total else 0

	data.append(
		{
			"label": _("Venta neta"),
			"estimated_cost": net_total,
			"currency": currency,
			"indent": 1,
		}
	)
	data.append(
		{
			"label": _("Costo laboral (horas)"),
			"estimated_cost": total_labor_cost,
			"currency": currency,
			"indent": 1,
		}
	)
	data.append(
		{
			"label": _("Costo items comprados/revendidos"),
			"estimated_cost": total_item_cost,
			"currency": currency,
			"indent": 1,
		}
	)
	data.append({"label": _("─" * 40), "indent": 1})
	data.append(
		{
			"label": _("Costo total estimado"),
			"estimated_cost": total_cost,
			"currency": currency,
			"bold": 1,
			"indent": 1,
		}
	)
	data.append(
		{
			"label": _("Margen estimado"),
			"estimated_cost": margin,
			"notes": "{:.1f}%".format(margin_pct),
			"currency": currency,
			"bold": 1,
			"indent": 1,
		}
	)

	# ── ADVERTENCIAS ─────────────────────────────────────────────────────
	all_warnings = bool(warnings or missing_activity or missing_rate or items_without_cost)
	if all_warnings:
		data.append(_spacer())
		data.append(_section(_("ADVERTENCIAS")))
		for w in warnings:
			data.append({"label": w, "indent": 1})
		if missing_activity:
			data.append(
				{
					"label": _(
						"⚠ {0} tarea(s) sin activity_type — costo laboral calculado parcialmente."
					).format(missing_activity),
					"indent": 1,
				}
			)
		if missing_rate:
			data.append(
				{
					"label": _(
						"⚠ {0} tarea(s) sin costing_rate — costo laboral calculado parcialmente."
					).format(missing_rate),
					"indent": 1,
				}
			)
		for item_name in items_without_cost:
			data.append(
				{
					"label": _(
						"⚠ {0} — sin Supplier Quotation, Buying Item Price, "
						"last_purchase_rate ni valuation_rate. Margen puede ser artificialmente alto."
					).format(item_name),
					"indent": 1,
				}
			)

	if all_warnings:
		data.append(
			{
				"label": _("El margen estimado puede estar artificialmente alto si hay costos faltantes."),
				"bold": 1,
				"indent": 1,
			}
		)

	return columns, data


def _get_item_cost(item_code: str):
	"""
	Returns (cost_per_unit, source_label) using ERPNext native sources.

	Priority:
	1. Supplier Quotation (most recent submitted)
	2. Buying Item Price (explicitly maintained)
	3. last_purchase_rate (historical)
	4. valuation_rate (stock — reflects inventory, not reposition cost)
	5. None → no cost available
	"""
	# 1. Supplier Quotation — most recent submitted
	sq = frappe.db.get_value(
		"Supplier Quotation Item",
		{"item_code": item_code, "docstatus": 1},
		"rate",
		order_by="creation desc",
	)
	if sq:
		return flt(sq), _("Supplier Quotation")

	# 2. Buying Item Price
	ip = frappe.db.get_value(
		"Item Price",
		{"item_code": item_code, "buying": 1, "selling": 0},
		"price_list_rate",
	)
	if ip:
		return flt(ip), _("Buying Item Price")

	# 3. last_purchase_rate
	lpr = frappe.db.get_value("Item", item_code, "last_purchase_rate")
	if lpr:
		return flt(lpr), _("Last Purchase Rate")

	# 4. valuation_rate (stock items only — reflects inventory cost, not reposition)
	vr = frappe.db.get_value("Item", item_code, "valuation_rate")
	if vr:
		return flt(vr), _("Valuation Rate")

	return None, None


def _get_columns():
	return [
		{
			"label": _("Fase / Concepto"),
			"fieldname": "label",
			"fieldtype": "Data",
			"width": 260,
		},
		{
			"label": _("Actividad"),
			"fieldname": "activity_type",
			"fieldtype": "Link",
			"options": "Activity Type",
			"width": 130,
		},
		{
			"label": _("Perfil"),
			"fieldname": "designation",
			"fieldtype": "Link",
			"options": "Designation",
			"width": 110,
		},
		{
			"label": _("Horas Est."),
			"fieldname": "estimated_hours",
			"fieldtype": "Float",
			"width": 85,
			"precision": 1,
		},
		{
			"label": _("$/hora / unit"),
			"fieldname": "costing_rate",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 100,
		},
		{
			"label": _("Costo Est. / Monto"),
			"fieldname": "estimated_cost",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"label": _("Notas / Fuente"),
			"fieldname": "notes",
			"fieldtype": "Data",
			"width": 240,
		},
	]


def _section(label: str) -> dict:
	return {"label": label, "bold": 1, "indent": 0}


def _phase_header(phase: str) -> dict:
	return {"label": phase, "bold": 1, "indent": 1}


def _spacer() -> dict:
	return {"label": _("")}
