# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Reporte Evaluación Económica (ADR-0018, Fase 2A).

Presenta el calendario económico por periodos relativos `Mes 0…N` calculado por
``utils.economic_calendar.get_economic_calendar`` (fuente única). On-demand; no persiste calendario.
Columnas por periodo: Ingreso / Costo externo / Costo laboral / Costo total / Margen; más un resumen
contractual (totales + margen %). Cobros/pagos/CAPEX financiero/VAN/TIR/FX quedan para Fase 2B/2C.
"""

import frappe
from frappe import _
from frappe.utils import flt

from erpnext_proposals.erpnext_proposals.utils.economic_calendar import get_economic_calendar


def execute(filters=None):
	filters = filters or {}
	quotation_name = filters.get("quotation")
	if not quotation_name:
		frappe.throw(_("Selecciona una Cotización para generar la Evaluación Económica."))

	data_model = get_economic_calendar(quotation_name)
	columns = _get_columns()
	rows = _build_rows(data_model)
	return columns, rows, None, None, _report_summary(data_model)


def _get_columns() -> list:
	return [
		{"fieldname": "period_label", "label": _("Periodo"), "fieldtype": "Data", "width": 120},
		{"fieldname": "revenue", "label": _("Ingreso"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "external", "label": _("Costo externo"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "labor", "label": _("Costo laboral"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "total_cost", "label": _("Costo total"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "margin", "label": _("Margen"), "fieldtype": "Currency", "width": 140},
	]


def _build_rows(model: dict) -> list:
	rows = []
	for p in model["periods"]:
		rows.append(
			{
				"period_label": _("Mes {0}").format(p["period"]),
				"revenue": flt(p["revenue"]),
				"external": flt(p["external"]),
				"labor": flt(p["labor"]),
				"total_cost": flt(p["total_cost"]),
				"margin": flt(p["margin"]),
			}
		)
	t = model["totals"]
	rows.append(
		{
			"period_label": _("Total contractual"),
			"revenue": flt(t["revenue"]),
			"external": flt(t["external"]),
			"labor": flt(t["labor"]),
			"total_cost": flt(t["total_cost"]),
			"margin": flt(t["margin"]),
		}
	)
	return rows


def _report_summary(model: dict) -> list:
	t = model["totals"]
	currency = model["currency"]
	return [
		{
			"label": _("Ingreso contractual"),
			"value": flt(t["revenue"]),
			"datatype": "Currency",
			"currency": currency,
		},
		{
			"label": _("Costo externo total"),
			"value": flt(t["external"]),
			"datatype": "Currency",
			"currency": currency,
		},
		{
			"label": _("Costo laboral total"),
			"value": flt(t["labor"]),
			"datatype": "Currency",
			"currency": currency,
		},
		{
			"label": _("Costo total"),
			"value": flt(t["total_cost"]),
			"datatype": "Currency",
			"currency": currency,
		},
		{
			"label": _("Margen total"),
			"value": flt(t["margin"]),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Green" if t["margin"] >= 0 else "Red",
		},
		{
			"label": _("Margen %"),
			"value": flt(t["margin_pct"]),
			"datatype": "Percent",
			"indicator": "Green" if t["margin"] >= 0 else "Red",
		},
	]
