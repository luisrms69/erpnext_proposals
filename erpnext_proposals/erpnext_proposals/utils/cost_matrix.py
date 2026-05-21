import random
import string

import frappe
from frappe import _
from frappe.utils import flt, now_datetime


@frappe.whitelist()
def rebuild_cost_matrix() -> dict:
	"""
	Rebuilds Proposal Cost Matrix from employee cost data.

	Source hierarchy per (designation, activity_type):
	  1. Activity Cost  — employee-level explicit rate
	  2. Timesheet Detail — historical average from real timesheets
	  3. Salary Structure Assignment — base/160h as hourly proxy

	Does NOT mix sources within the same (designation, activity_type) pair.
	Updates existing records; does not wipe the table between runs.
	Creates a Proposal Cost Matrix Log entry on every real rate change,
	and on first insert (old_rate=0).
	Returns a summary dict.
	"""
	run_id = _generate_run_id()
	created = updated = skipped = logged = 0

	activity_rows = _fetch_activity_cost_data()
	timesheet_rows = _fetch_timesheet_data()
	salary_rows = _fetch_salary_data()

	activity_keys = {(r.designation, r.activity_type) for r in activity_rows}
	timesheet_keys = {(r.designation, r.activity_type) for r in timesheet_rows}
	covered_by_upper = activity_keys | timesheet_keys

	for row in activity_rows:
		notes = _single_employee_note(row.employee_count)
		c, u, l = _upsert(
			designation=row.designation,
			activity_type=row.activity_type,
			is_general_rate=0,
			avg_costing_rate=flt(row.avg_costing_rate),
			avg_billing_rate=flt(row.avg_billing_rate),
			employee_count=int(row.employee_count or 0),
			source="activity_cost",
			status="warning" if row.employee_count == 1 else "ok",
			notes=notes,
			run_id=run_id,
		)
		created += c
		updated += u
		logged += l

	for row in timesheet_rows:
		if (row.designation, row.activity_type) in activity_keys:
			skipped += 1
			continue
		notes = _single_employee_note(row.employee_count)
		c, u, l = _upsert(
			designation=row.designation,
			activity_type=row.activity_type,
			is_general_rate=0,
			avg_costing_rate=flt(row.avg_costing_rate),
			avg_billing_rate=flt(row.avg_billing_rate),
			employee_count=int(row.employee_count or 0),
			source="timesheet",
			status="warning" if row.employee_count == 1 else "ok",
			notes=notes,
			run_id=run_id,
		)
		created += c
		updated += u
		logged += l

	for row in salary_rows:
		if (row.designation, None) in covered_by_upper:
			skipped += 1
			continue
		has_upper = any(d == row.designation for (d, _) in covered_by_upper)
		if has_upper:
			skipped += 1
			continue
		c, u, l = _upsert(
			designation=row.designation,
			activity_type=None,
			is_general_rate=1,
			avg_costing_rate=flt(row.avg_costing_rate),
			avg_billing_rate=0.0,
			employee_count=int(row.employee_count or 0),
			source="salary",
			status="warning",
			notes=_("Proxy salarial (base/160h) — validar contra tarifa real"),
			run_id=run_id,
		)
		created += c
		updated += u
		logged += l

	_rebuild_general_rates(run_id)

	frappe.db.sql(
		"UPDATE `tabProposal Cost Matrix` SET status=%s WHERE avg_costing_rate = 0 OR avg_costing_rate IS NULL",
		("sin_datos",),
	)

	frappe.db.commit()  # nosemgrep

	return {
		"created": created,
		"updated": updated,
		"skipped": skipped,
		"logged": logged,
		"run_id": run_id,
	}


def get_designation_cost(designation: str, activity_type: str) -> tuple:
	"""
	Returns (costing_rate, source_label) for use in profitability calculations.

	Lookup order:
	1. Proposal Cost Matrix exact match (designation + activity_type)
	2. Proposal Cost Matrix general rate (designation only, is_general_rate=1)
	3. Activity Type.costing_rate (legacy fallback)
	4. (0.0, 'sin_datos')
	"""
	if designation:
		if activity_type:
			row = frappe.db.get_value(
				"Proposal Cost Matrix",
				{
					"designation": designation,
					"activity_type": activity_type,
					"status": ["in", ["ok", "warning"]],
				},
				"avg_costing_rate",
			)
			if row:
				return flt(row), "matrix"

		gen_row = frappe.db.get_value(
			"Proposal Cost Matrix",
			{"designation": designation, "is_general_rate": 1, "status": ["in", ["ok", "warning"]]},
			"avg_costing_rate",
		)
		if gen_row:
			return flt(gen_row), "matrix_general"

	if activity_type:
		at_rate = flt(frappe.db.get_value("Activity Type", activity_type, "costing_rate") or 0)
		if at_rate:
			return at_rate, "activity_type"

	return 0.0, "sin_datos"


def is_matrix_populated() -> bool:
	"""Returns True if the matrix has at least one usable row."""
	return bool(frappe.db.count("Proposal Cost Matrix", {"status": ["in", ["ok", "warning"]]}))


def get_matrix_last_updated():
	"""Returns the oldest last_updated datetime in the matrix, or None."""
	return frappe.db.get_value(
		"Proposal Cost Matrix",
		{},
		"last_updated",
		order_by="last_updated asc",
	)


# ── Private helpers ──────────────────────────────────────────────────────────


def _generate_run_id() -> str:
	"""Generates a unique run identifier. Format: REBUILD-YYYYMMDD-HHMMSS-XXXX."""
	ts = now_datetime().strftime("%Y%m%d-%H%M%S")
	suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
	return f"REBUILD-{ts}-{suffix}"


def _log_rate_change(
	designation: str,
	activity_type: str | None,
	is_general_rate: int,
	old_rate: float,
	new_rate: float,
	source: str,
	employee_count: int,
	run_id: str,
	notes: str,
) -> None:
	frappe.get_doc(
		{
			"doctype": "Proposal Cost Matrix Log",
			"designation": designation,
			"activity_type": activity_type or None,
			"is_general_rate": is_general_rate,
			"old_rate": flt(old_rate),
			"new_rate": flt(new_rate),
			"source": source,
			"employee_count": employee_count,
			"changed_on": now_datetime(),
			"rebuild_run_id": run_id,
			"notes": notes,
		}
	).insert(ignore_permissions=True)


def _upsert(
	designation: str,
	activity_type: str | None,
	is_general_rate: int,
	avg_costing_rate: float,
	avg_billing_rate: float,
	employee_count: int,
	source: str,
	status: str,
	notes: str,
	run_id: str,
) -> tuple:
	"""Create or update one Proposal Cost Matrix row. Returns (created, updated, logged)."""
	filters = {"designation": designation, "is_general_rate": is_general_rate}
	if activity_type:
		filters["activity_type"] = activity_type
	else:
		filters["activity_type"] = ["is", "not set"]

	existing = frappe.db.get_value(
		"Proposal Cost Matrix", filters, ["name", "avg_costing_rate"], as_dict=True
	)
	now = now_datetime()

	if existing:
		old_rate = flt(existing.avg_costing_rate)
		rate_changed = abs(old_rate - avg_costing_rate) > 0.01

		update_values = {
			"avg_costing_rate": avg_costing_rate,
			"avg_billing_rate": avg_billing_rate,
			"employee_count": employee_count,
			"source": source,
			"status": status,
			"last_updated": now,
			"notes": notes,
		}
		if rate_changed:
			update_values["rate_changed_on"] = now

		frappe.db.set_value("Proposal Cost Matrix", existing.name, update_values, update_modified=False)

		if rate_changed:
			_log_rate_change(
				designation,
				activity_type,
				is_general_rate,
				old_rate,
				avg_costing_rate,
				source,
				employee_count,
				run_id,
				notes,
			)
			return 0, 1, 1

		return 0, 1, 0

	doc = frappe.get_doc(
		{
			"doctype": "Proposal Cost Matrix",
			"designation": designation,
			"activity_type": activity_type or None,
			"is_general_rate": is_general_rate,
			"avg_costing_rate": avg_costing_rate,
			"avg_billing_rate": avg_billing_rate,
			"employee_count": employee_count,
			"source": source,
			"status": status,
			"last_updated": now,
			"rate_changed_on": now,
			"notes": notes,
		}
	)
	doc.insert(ignore_permissions=True)

	# Log first insert with old_rate=0
	_log_rate_change(
		designation,
		activity_type,
		is_general_rate,
		0.0,
		avg_costing_rate,
		source,
		employee_count,
		run_id,
		_("Primera vez") if not notes else f"{_('Primera vez')} — {notes}",
	)
	return 1, 0, 1


def _rebuild_general_rates(run_id: str) -> None:
	"""
	For each designation that has specific activity_type rows,
	create/update one is_general_rate=1 row with the weighted average.
	"""
	rows = frappe.db.sql(
		"""
        SELECT
            designation,
            AVG(avg_costing_rate) AS avg_costing_rate,
            AVG(avg_billing_rate) AS avg_billing_rate,
            SUM(employee_count) AS employee_count,
            MIN(source) AS source
        FROM `tabProposal Cost Matrix`
        WHERE is_general_rate = 0
            AND avg_costing_rate > 0
        GROUP BY designation
        """,
		as_dict=True,
	)
	for row in rows:
		_upsert(
			designation=row.designation,
			activity_type=None,
			is_general_rate=1,
			avg_costing_rate=flt(row.avg_costing_rate),
			avg_billing_rate=flt(row.avg_billing_rate),
			employee_count=int(row.employee_count or 0),
			source=row.source,
			status="ok",
			notes="",
			run_id=run_id,
		)


def _fetch_activity_cost_data() -> list:
	return frappe.db.sql(
		"""
        SELECT
            e.designation,
            ac.activity_type,
            AVG(ac.costing_rate) AS avg_costing_rate,
            AVG(COALESCE(ac.billing_rate, 0)) AS avg_billing_rate,
            COUNT(DISTINCT ac.employee) AS employee_count
        FROM `tabActivity Cost` ac
        INNER JOIN `tabEmployee` e ON e.name = ac.employee
        WHERE e.status = 'Active'
            AND e.designation IS NOT NULL
            AND e.designation != ''
            AND ac.costing_rate > 0
        GROUP BY e.designation, ac.activity_type
        """,
		as_dict=True,
	)


def _fetch_timesheet_data() -> list:
	return frappe.db.sql(
		"""
        SELECT
            e.designation,
            td.activity_type,
            AVG(td.costing_rate) AS avg_costing_rate,
            AVG(COALESCE(td.billing_rate, 0)) AS avg_billing_rate,
            COUNT(DISTINCT ts.employee) AS employee_count
        FROM `tabTimesheet Detail` td
        INNER JOIN `tabTimesheet` ts ON ts.name = td.parent
        INNER JOIN `tabEmployee` e ON e.name = ts.employee
        WHERE e.status = 'Active'
            AND e.designation IS NOT NULL
            AND e.designation != ''
            AND td.costing_rate > 0
        GROUP BY e.designation, td.activity_type
        """,
		as_dict=True,
	)


def _fetch_salary_data() -> list:
	# Salary Structure Assignment requires HRMS — gracefully skip if not installed
	if not frappe.db.table_exists("Salary Structure Assignment"):
		return []
	return frappe.db.sql(
		"""
        SELECT
            ssa.designation,
            AVG(ssa.base) / 160.0 AS avg_costing_rate,
            COUNT(DISTINCT ssa.employee) AS employee_count
        FROM `tabSalary Structure Assignment` ssa
        WHERE ssa.docstatus = 1
            AND ssa.designation IS NOT NULL
            AND ssa.designation != ''
            AND ssa.base > 0
        GROUP BY ssa.designation
        """,
		as_dict=True,
	)


def _single_employee_note(count: int) -> str:
	if int(count or 0) == 1:
		return _("Solo 1 empleado con datos — tasa puede no ser representativa")
	return ""
