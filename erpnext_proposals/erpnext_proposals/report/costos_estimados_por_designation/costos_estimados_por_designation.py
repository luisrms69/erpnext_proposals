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
			"width": 160,
		},
		{
			"label": _("Tasa General"),
			"fieldname": "is_general_rate",
			"fieldtype": "Check",
			"width": 90,
		},
		{
			"label": _("Costo/hora"),
			"fieldname": "avg_costing_rate",
			"fieldtype": "Currency",
			"width": 120,
		},
		{
			"label": _("Precio/hora"),
			"fieldname": "avg_billing_rate",
			"fieldtype": "Currency",
			"width": 120,
		},
		{
			"label": _("Empleados"),
			"fieldname": "employee_count",
			"fieldtype": "Int",
			"width": 80,
		},
		{
			"label": _("Fuente"),
			"fieldname": "source",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Estado"),
			"fieldname": "status",
			"fieldtype": "Data",
			"width": 80,
		},
		{
			"label": _("Última Actualización"),
			"fieldname": "last_updated",
			"fieldtype": "Datetime",
			"width": 130,
		},
		{
			"label": _("Última Variación"),
			"fieldname": "rate_changed_on",
			"fieldtype": "Datetime",
			"width": 130,
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

	if filters.get("status"):
		conditions.append("status = %(status)s")
		values["status"] = filters["status"]

	if filters.get("source"):
		conditions.append("source = %(source)s")
		values["source"] = filters["source"]

	query = """
		SELECT
			designation, activity_type, is_general_rate,
			avg_costing_rate, avg_billing_rate, employee_count,
			source, status, last_updated, rate_changed_on, notes
		FROM `tabProposal Cost Matrix`
	"""
	if conditions:
		query += " WHERE " + " AND ".join(conditions)
	query += " ORDER BY designation, is_general_rate DESC, activity_type"

	rows = frappe.db.sql(query, values=values, as_dict=True)

	if not rows:
		frappe.msgprint(
			_("La Proposal Cost Matrix está vacía. Ejecuta 'Recalcular Costos' para poblarla."),
			alert=True,
			indicator="orange",
		)

	return rows
