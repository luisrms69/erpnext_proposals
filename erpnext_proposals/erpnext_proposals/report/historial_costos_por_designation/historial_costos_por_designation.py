import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	return _get_columns(), _get_data(filters or {})


def _get_columns():
	return [
		{
			"label": _("Designation"),
			"fieldname": "designation",
			"fieldtype": "Link",
			"options": "Designation",
			"width": 160,
		},
		{
			"label": _("Tipo de Actividad"),
			"fieldname": "activity_type",
			"fieldtype": "Link",
			"options": "Activity Type",
			"width": 150,
		},
		{
			"label": _("Tasa General"),
			"fieldname": "is_general_rate",
			"fieldtype": "Check",
			"width": 85,
		},
		{
			"label": _("Tasa Anterior"),
			"fieldname": "old_rate",
			"fieldtype": "Currency",
			"width": 110,
		},
		{
			"label": _("Tasa Nueva"),
			"fieldname": "new_rate",
			"fieldtype": "Currency",
			"width": 110,
		},
		{
			"label": _("Variación"),
			"fieldname": "change_amount",
			"fieldtype": "Currency",
			"width": 100,
		},
		{
			"label": _("Variación %"),
			"fieldname": "change_percent",
			"fieldtype": "Percent",
			"width": 90,
		},
		{
			"label": _("Fuente"),
			"fieldname": "source",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Empleados"),
			"fieldname": "employee_count",
			"fieldtype": "Int",
			"width": 80,
		},
		{
			"label": _("Fecha del cambio"),
			"fieldname": "changed_on",
			"fieldtype": "Datetime",
			"width": 140,
		},
		{
			"label": _("Rebuild Run ID"),
			"fieldname": "rebuild_run_id",
			"fieldtype": "Data",
			"width": 170,
		},
		{
			"label": _("Notas"),
			"fieldname": "notes",
			"fieldtype": "Data",
			"width": 220,
		},
	]


def _get_data(filters: dict) -> list:
	conditions = []
	values = {}

	if filters.get("designation"):
		conditions.append("designation = %(designation)s")
		values["designation"] = filters["designation"]

	if filters.get("activity_type"):
		conditions.append("activity_type = %(activity_type)s")
		values["activity_type"] = filters["activity_type"]

	if filters.get("from_date"):
		conditions.append("changed_on >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("changed_on <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

	rows = frappe.db.sql(
		f"""
        SELECT
            designation,
            activity_type,
            is_general_rate,
            old_rate,
            new_rate,
            source,
            employee_count,
            changed_on,
            rebuild_run_id,
            notes
        FROM `tabProposal Cost Matrix Log`
        {where}
        ORDER BY designation, activity_type, changed_on DESC
        """,
		values=values,
		as_dict=True,
	)

	for row in rows:
		old = flt(row.old_rate)
		new = flt(row.new_rate)
		row["change_amount"] = new - old
		# Avoid division by zero: show None when old_rate is 0
		row["change_percent"] = ((new - old) / old * 100) if old else None

	if not rows:
		frappe.msgprint(
			_(
				"No hay registros en el historial. El historial se llena automáticamente al ejecutar 'Recalcular Costos'."
			),
			alert=True,
			indicator="orange",
		)

	return rows
