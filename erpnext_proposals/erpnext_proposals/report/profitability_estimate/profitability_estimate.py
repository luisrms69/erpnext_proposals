import frappe
from frappe import _
from frappe.utils import flt

from erpnext_proposals.erpnext_proposals.utils.cost_matrix import (
	get_designation_cost,
	get_matrix_last_updated,
	is_matrix_populated,
)
from erpnext_proposals.erpnext_proposals.utils.phase import phase_label, phase_sequence

TOLERANCE = 0.01  # tolerance for Q/C numeric checks


def execute(filters=None):
	filters = filters or {}
	quotation_name = filters.get("quotation")

	if not quotation_name:
		frappe.throw(_("Selecciona una Cotizacion para generar el reporte."))

	d = get_profitability_data(quotation_name)
	return _get_columns(), _build_report_rows(d)


def get_profitability_data(quotation_name: str) -> dict:
	"""
	Central calculation function.
	Used by: Script Report execute() and Print Format Rentabilidad Estimada.
	Single source of truth for profitability calculation.
	"""
	quotation = frappe.get_doc("Quotation", quotation_name)
	quotation.check_permission("read")

	currency = quotation.currency or "MXN"
	company_currency = (
		frappe.db.get_value("Company", quotation.company, "default_currency") if quotation.company else None
	)

	elaborated_by_name = frappe.db.get_value("User", quotation.owner, "full_name") if quotation.owner else ""

	# Items that have Scope Items → costed by labor, not by purchase price
	items_with_scope = {
		row.item_code for row in quotation.quotation_scope_items if row.include_in_proposal and row.item_code
	}

	# ── Labor cost ───────────────────────────────────────────────────────
	scope_rows_raw = sorted(
		[r for r in quotation.quotation_scope_items if r.include_in_proposal],
		key=lambda r: (phase_sequence(r.phase), r.sequence or 0, r.idx),
	)

	labor_rows = []
	total_labor_hours = 0.0
	total_labor_cost = 0.0
	missing_activity = 0
	missing_rate = 0
	missing_designation = 0
	missing_frozen_snapshot = 0
	is_submitted = quotation.docstatus == 1

	for row in scope_rows_raw:
		# Use frozen snapshot for submitted quotations; recalculate for drafts.
		use_frozen = is_submitted and row.rate_locked and flt(row.costing_rate)

		if use_frozen:
			costing_rate = flt(row.costing_rate)
			rate_source = row.rate_source or "frozen"
			notes = rate_source
		else:
			if is_submitted and not row.rate_locked:
				missing_frozen_snapshot += 1
			costing_rate, rate_source = get_designation_cost(row.designation, row.activity_type)
			notes = rate_source

			if rate_source == "sin_datos":
				missing_rate += 1
				if not row.designation and not row.activity_type:
					missing_activity += 1
					missing_designation += 1
					notes = "sin_designation_ni_activity"
				elif not row.designation:
					missing_designation += 1
					notes = "sin_designation"
				elif not row.activity_type:
					missing_activity += 1
					notes = "sin_activity_type"
				else:
					notes = "sin_costing_rate"
			elif not row.designation:
				missing_designation += 1

		hours = flt(row.estimated_hours or 0)
		cost = flt(hours * costing_rate)
		total_labor_hours += hours
		total_labor_cost += cost

		labor_rows.append(
			{
				"phase": row.phase or "",
				"title": row.title or row.code,
				"activity_type": row.activity_type or "",
				"designation": row.designation or "",
				"hours": hours,
				"costing_rate": costing_rate,
				"cost": cost,
				"notes": notes,
			}
		)

	# ── Item cost ────────────────────────────────────────────────────────
	item_cost_rows = []
	total_item_cost = 0.0
	items_without_cost = []

	for item in quotation.items:
		if item.item_code in items_with_scope:
			item_cost_rows.append(
				{
					"item_name": item.item_name,
					"item_code": item.item_code,
					"qty": flt(item.qty),
					"cost_per_unit": 0.0,
					"total_cost": 0.0,
					"source": "scope",
					"covered_by_scope": True,
				}
			)
			continue

		cost_per_unit, source = _get_item_cost(item.item_code)
		qty = flt(item.qty)

		if cost_per_unit is None:
			items_without_cost.append(item.item_name)
			item_cost_rows.append(
				{
					"item_name": item.item_name,
					"item_code": item.item_code,
					"qty": qty,
					"cost_per_unit": 0.0,
					"total_cost": 0.0,
					"source": "sin_costo",
					"covered_by_scope": False,
				}
			)
			continue

		item_total = flt(qty * cost_per_unit)
		total_item_cost += item_total

		item_cost_rows.append(
			{
				"item_name": item.item_name,
				"item_code": item.item_code,
				"qty": qty,
				"cost_per_unit": cost_per_unit,
				"total_cost": item_total,
				"source": source,
				"covered_by_scope": False,
			}
		)

	# ── Sales rows ───────────────────────────────────────────────────────
	sales_rows = [
		{
			"item_name": item.item_name,
			"qty": flt(item.qty),
			"rate": flt(item.rate),
			"net_amount": flt(item.net_amount),
		}
		for item in quotation.items
	]

	# ── Totals ───────────────────────────────────────────────────────────
	net_total = flt(quotation.net_total)
	taxes = flt(quotation.total_taxes_and_charges)
	grand_total = flt(quotation.grand_total)
	total_cost = total_labor_cost + total_item_cost
	margin = net_total - total_cost
	margin_pct = (margin / net_total * 100) if net_total else 0.0

	# ── Warnings ─────────────────────────────────────────────────────────
	warnings = []

	# Matrix health warnings
	if not is_matrix_populated():
		warnings.append(
			_(
				"Tabla Proposal Cost Matrix vacía — ejecutar 'Recalcular Costos' desde el reporte en el workspace."
			)
		)
	else:
		oldest = get_matrix_last_updated()
		if oldest:
			from frappe.utils import now_datetime

			days_old = (now_datetime() - oldest).days
			if days_old > 30:
				warnings.append(
					_("Costos por Designation desactualizados — última actualización hace {0} días.").format(
						days_old
					)
				)

	if company_currency and currency != company_currency:
		warnings.append(
			_("Moneda de Quotation ({0}) distinta a moneda base ({1}) — comparacion no confiable.").format(
				currency, company_currency
			)
		)
	if missing_frozen_snapshot:
		warnings.append(
			_(
				"{0} tarea(s) de propuesta enviada sin costo congelado — usando tasa vigente como aproximación."
			).format(missing_frozen_snapshot)
		)
	if missing_designation:
		warnings.append(
			_("{0} tarea(s) sin Designation — costo por perfil no disponible.").format(missing_designation)
		)
	if missing_activity:
		warnings.append(
			_("{0} tarea(s) sin activity_type ni Designation — sin fuente de costo.").format(missing_activity)
		)
	if missing_rate:
		warnings.append(
			_("{0} tarea(s) sin costing_rate — costo laboral calculado parcialmente.").format(missing_rate)
		)
	for name in items_without_cost:
		warnings.append(
			_(
				"{0} — sin Supplier Quotation, Buying Item Price, last_purchase_rate ni valuation_rate."
			).format(name)
		)

	# ── Q/C checks ───────────────────────────────────────────────────────
	sum_net_amounts = sum(flt(i.net_amount) for i in quotation.items)

	qc_checks = [
		{
			"label": _("Venta neta cuadra con Quotation.net_total"),
			"status": "ok" if abs(sum_net_amounts - net_total) <= TOLERANCE else "warning",
			"detail": "{:,.2f} vs {:,.2f}".format(sum_net_amounts, net_total),
		},
		{
			"label": _("Tareas sin Designation"),
			"status": "ok" if missing_designation == 0 else "warning",
			"detail": str(missing_designation),
		},
		{
			"label": _("Tareas sin activity_type"),
			"status": "ok" if missing_activity == 0 else "warning",
			"detail": str(missing_activity),
		},
		{
			"label": _("Tareas sin costing_rate"),
			"status": "ok" if missing_rate == 0 else "warning",
			"detail": str(missing_rate),
		},
		{
			"label": _("Items sin costo estimable"),
			"status": "ok" if not items_without_cost else "warning",
			"detail": str(len(items_without_cost)),
		},
		{
			"label": _("Moneda Quotation = moneda base Company"),
			"status": "ok" if (not company_currency or currency == company_currency) else "warning",
			"detail": "{} / {}".format(currency, company_currency or "—"),
		},
	]

	return {
		"quotation_meta": {
			"name": quotation.name,
			"proposal_title": quotation.proposal_title or quotation.name,
			"customer_name": quotation.customer_name or quotation.party_name or "—",
			"transaction_date": quotation.transaction_date,
			"valid_till": quotation.valid_till,
			"currency": currency,
			"company": quotation.company,
			"company_currency": company_currency or currency,
			"payment_terms_template": quotation.payment_terms_template or "",
			"elaborated_by": elaborated_by_name,
		},
		"labor_rows": labor_rows,
		"item_cost_rows": item_cost_rows,
		"sales_rows": sales_rows,
		"totals": {
			"labor_hours": total_labor_hours,
			"labor_cost": total_labor_cost,
			"item_cost": total_item_cost,
			"total_cost": total_cost,
			"net_total": net_total,
			"taxes": taxes,
			"grand_total": grand_total,
			"margin": margin,
			"margin_pct": margin_pct,
		},
		"warnings": warnings,
		"qc_checks": qc_checks,
	}


def _get_item_cost(item_code: str):
	"""
	Returns (cost_per_unit, source_label) from ERPNext native sources.
	Priority: Supplier Quotation > Buying Item Price > last_purchase_rate > valuation_rate
	"""
	sq = frappe.db.get_value(
		"Supplier Quotation Item",
		{"item_code": item_code, "docstatus": 1},
		"rate",
		order_by="creation desc",
	)
	if sq:
		return flt(sq), _("Supplier Quotation")

	ip = frappe.db.get_value(
		"Item Price",
		{"item_code": item_code, "buying": 1, "selling": 0},
		"price_list_rate",
	)
	if ip:
		return flt(ip), _("Buying Item Price")

	lpr = frappe.db.get_value("Item", item_code, "last_purchase_rate")
	if lpr:
		return flt(lpr), _("Último precio de compra")

	vr = frappe.db.get_value("Item", item_code, "valuation_rate")
	if vr:
		return flt(vr), _("Valuation Rate")

	return None, None


def _build_report_rows(d: dict) -> list:
	"""Formats get_profitability_data() output as Script Report rows."""
	data = []
	currency = d["quotation_meta"]["currency"]

	# Labor section
	data.append(_section(_("COSTO LABORAL (Horas estimadas)")))
	current_phase = None
	for row in d["labor_rows"]:
		if row["phase"] != current_phase:
			current_phase = row["phase"]
			if current_phase:
				data.append(_phase_header(phase_label(current_phase)))
		notes_map = {
			"sin_activity_type": _("sin activity_type"),
			"sin_costing_rate": _("sin costing_rate"),
		}
		data.append(
			{
				"label": row["title"],
				"activity_type": row["activity_type"],
				"designation": row["designation"],
				"estimated_hours": row["hours"] or None,
				"costing_rate": row["costing_rate"] or None,
				"estimated_cost": row["cost"] or None,
				"notes": notes_map.get(row["notes"], row["notes"]),
				"currency": currency,
				"indent": 2,
			}
		)
	data.append(
		{
			"label": _("Total costo laboral"),
			"estimated_hours": d["totals"]["labor_hours"],
			"estimated_cost": d["totals"]["labor_cost"],
			"currency": currency,
			"bold": 1,
			"indent": 1,
		}
	)

	# Items section — only items NOT covered by labor scope
	data.append(_spacer())
	data.append(_section(_("ITEMS COMPRADOS / REVENDIDOS")))
	for row in d["item_cost_rows"]:
		if row["covered_by_scope"]:
			continue  # cost already captured in labor section
		elif row["source"] == "sin_costo":
			data.append(
				{
					"label": row["item_name"],
					"notes": _("sin costo estimable"),
					"currency": currency,
					"indent": 1,
				}
			)
		else:
			data.append(
				{
					"label": row["item_name"],
					"costing_rate": row["cost_per_unit"],
					"estimated_cost": row["total_cost"],
					"notes": _("Fuente: {0} | Cant: {1}").format(row["source"], flt(row["qty"], 2)),
					"currency": currency,
					"indent": 1,
				}
			)
	data.append(
		{
			"label": _("Total costo items"),
			"estimated_cost": d["totals"]["item_cost"],
			"currency": currency,
			"bold": 1,
			"indent": 1,
		}
	)

	# Sales section
	data.append(_spacer())
	data.append(_section(_("VENTA (Quotation Items)")))
	for row in d["sales_rows"]:
		data.append(
			{
				"label": row["item_name"],
				"notes": _("Cant: {0} x {1}").format(
					flt(row["qty"], 2), frappe.format_value(row["rate"], {"fieldtype": "Currency"})
				),
				"estimated_cost": row["net_amount"],
				"currency": currency,
				"indent": 1,
			}
		)
	t = d["totals"]
	data.append(
		{
			"label": _("Venta neta"),
			"estimated_cost": t["net_total"],
			"currency": currency,
			"bold": 1,
			"indent": 1,
		}
	)
	data.append(
		{
			"label": _("Impuestos (informativo)"),
			"estimated_cost": t["taxes"],
			"notes": _("Solo informativo"),
			"currency": currency,
			"indent": 1,
		}
	)
	data.append(
		{
			"label": _("Total con impuestos (informativo)"),
			"estimated_cost": t["grand_total"],
			"notes": _("Solo informativo"),
			"currency": currency,
			"indent": 1,
		}
	)

	# Profitability summary
	data.append(_spacer())
	data.append(_section(_("RENTABILIDAD ESTIMADA")))
	data.append(
		{"label": _("Venta neta"), "estimated_cost": t["net_total"], "currency": currency, "indent": 1}
	)
	data.append(
		{
			"label": _("Costo laboral (horas)"),
			"estimated_cost": t["labor_cost"],
			"currency": currency,
			"indent": 1,
		}
	)
	data.append(
		{
			"label": _("Costo items comprados/revendidos"),
			"estimated_cost": t["item_cost"],
			"currency": currency,
			"indent": 1,
		}
	)
	data.append({"label": _("─" * 40), "indent": 1})
	data.append(
		{
			"label": _("Costo total estimado"),
			"estimated_cost": t["total_cost"],
			"currency": currency,
			"bold": 1,
			"indent": 1,
		}
	)
	data.append(
		{
			"label": _("Margen estimado"),
			"estimated_cost": t["margin"],
			"notes": "{:.1f}%".format(t["margin_pct"]),
			"currency": currency,
			"bold": 1,
			"indent": 1,
		}
	)

	# Warnings
	all_warn = d["warnings"]
	if all_warn:
		data.append(_spacer())
		data.append(_section(_("ADVERTENCIAS")))
		for w in all_warn:
			data.append({"label": w, "indent": 1})
		data.append(
			{
				"label": _("El margen estimado puede estar artificialmente alto si hay costos faltantes."),
				"bold": 1,
				"indent": 1,
			}
		)

	return data


def _get_columns():
	return [
		{"label": _("Fase / Concepto"), "fieldname": "label", "fieldtype": "Data", "width": 260},
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
		{"label": _("Notas / Fuente"), "fieldname": "notes", "fieldtype": "Data", "width": 240},
	]


def _section(label: str) -> dict:
	return {"label": label, "bold": 1, "indent": 0}


def _phase_header(phase: str) -> dict:
	return {"label": phase, "bold": 1, "indent": 1}


def _spacer() -> dict:
	return {"label": None}
