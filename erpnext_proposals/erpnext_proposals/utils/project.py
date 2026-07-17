import frappe
from frappe import _

from erpnext_proposals.erpnext_proposals.utils.permissions import assert_can_manage_proposals
from erpnext_proposals.erpnext_proposals.utils.phase import phase_label, phase_sequence


@frappe.whitelist()
def create_project_from_quotation(quotation_name: str):
	assert_can_manage_proposals()

	from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import (
		assert_can_create_project,
	)

	quotation = frappe.get_doc("Quotation", quotation_name)
	assert_can_create_project(quotation)  # validates docstatus, state, superseded, project

	if not quotation.proposal_template:
		frappe.throw(_("La Cotización no tiene Proposal Template asignado."))

	# Filas ejecutables: vendibles O internas de costo (participan en costo y Tasks).
	exec_rows = [
		r for r in quotation.quotation_scope_items if r.include_in_proposal or r.is_internal_cost_task
	]
	if not exec_rows:
		frappe.throw(
			_(
				"No hay actividades ejecutables (visibles o internas de costo) en esta propuesta. "
				"Una propuesta de solo licenciamiento no genera Proyecto."
			)
		)

	# Toda fila ejecutable debe tener fase — bloqueo explícito (no se inventa fase ni Task suelta).
	rows_sin_fase = [r for r in exec_rows if not r.phase]
	if rows_sin_fase:
		nombres = ", ".join((r.title or r.code or r.scope_item or "?") for r in rows_sin_fase[:5])
		frappe.throw(
			_(
				"No se puede crear el Proyecto: {0} actividad(es) ejecutable(s) sin fase asignada ({1}). "
				"Asigne una Proposal Phase a todas las actividades ejecutables antes de crear el Proyecto."
			).format(len(rows_sin_fase), nombres)
		)

	# ── Project (idempotente: reutiliza si ya existe) ──────────────────────────
	if quotation.proposal_project and frappe.db.exists("Project", quotation.proposal_project):
		project = frappe.get_doc("Project", quotation.proposal_project)
	else:
		customer = quotation.party_name
		customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
		project_name = quotation.proposal_title or f"{customer_name} — {quotation.proposal_group}"
		# Recovery: reutiliza si el Project existe pero la referencia no se guardó (fallo parcial).
		if frappe.db.exists("Project", project_name):
			project = frappe.get_doc("Project", project_name)
		else:
			project = frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": project_name,
					"company": quotation.company,
					"customer": customer,
					"cost_center": quotation.proposal_cost_center or None,
					"expected_start_date": quotation.transaction_date,
					"status": "Open",
				}
			)
			project.insert(ignore_permissions=True)
		frappe.db.set_value(
			"Quotation", quotation_name, "proposal_project", project.name, update_modified=False
		)

	# ── Tasks jerárquicas: Task-fase (padre, is_group) → Task-hija (Scope Item) ──
	counters = {"parent_created": 0, "parent_reused": 0, "tasks_created": 0, "tasks_skipped": 0}
	phase_task_by_code: dict = {}

	def _phase_parent_task(phase_code: str) -> str:
		"""Task-fase: una por (Project, Proposal Phase). Idempotente."""
		if phase_code in phase_task_by_code:
			return phase_task_by_code[phase_code]
		existing = frappe.db.get_value(
			"Task", {"project": project.name, "proposal_phase": phase_code, "is_group": 1}, "name"
		)
		if existing:
			counters["parent_reused"] += 1
			phase_task_by_code[phase_code] = existing
			return existing
		parent = frappe.get_doc(
			{
				"doctype": "Task",
				"subject": phase_label(phase_code),
				"project": project.name,
				"is_group": 1,
				"expected_time": 0,
				"status": "Open",
				"proposal_phase": phase_code,
				"source_quotation": quotation.name,
			}
		)
		parent.insert(ignore_permissions=True)
		counters["parent_created"] += 1
		phase_task_by_code[phase_code] = parent.name
		return parent.name

	# Orden: fases por Proposal Phase.sequence, luego secuencia del scope, luego idx.
	exec_rows.sort(key=lambda r: (phase_sequence(r.phase), r.sequence or 0, r.idx))

	for row in exec_rows:
		# Idempotencia de la hija: por referencia guardada o por trazabilidad.
		if row.project_task and frappe.db.exists("Task", row.project_task):
			counters["tasks_skipped"] += 1
			continue
		existing_child = frappe.db.get_value(
			"Task", {"project": project.name, "source_quotation_scope_item": row.name}, "name"
		)
		if existing_child:
			frappe.db.set_value(
				"Quotation Scope Item", row.name, "project_task", existing_child, update_modified=False
			)
			counters["tasks_skipped"] += 1
			continue

		parent = _phase_parent_task(row.phase)
		subject = f"{row.title or row.code} — {row.item_code}" if row.item_code else (row.title or row.code)

		desc_parts = []
		if row.description:
			desc_parts.append(row.description)
		if row.deliverable:
			desc_parts.append(f"<p><strong>Entregable:</strong></p>{row.deliverable}")
		if row.activity_type:
			desc_parts.append(f"<p><strong>Tipo de actividad:</strong> {row.activity_type}</p>")
		if row.designation:
			desc_parts.append(f"<p><strong>Perfil:</strong> {row.designation}</p>")

		task = frappe.get_doc(
			{
				"doctype": "Task",
				"subject": subject,
				"project": project.name,
				"parent_task": parent,
				"is_group": 0,
				"expected_time": row.estimated_hours or 0,
				"description": "".join(desc_parts),
				"status": "Open",
				"source_quotation_scope_item": row.name,
			}
		)
		task.insert(ignore_permissions=True)
		counters["tasks_created"] += 1
		frappe.db.set_value(
			"Quotation Scope Item", row.name, "project_task", task.name, update_modified=False
		)

	frappe.db.commit()  # nosemgrep

	return {
		"project": project.name,
		"parent_tasks_created": counters["parent_created"],
		"parent_tasks_reused": counters["parent_reused"],
		"tasks_created": counters["tasks_created"],
		"tasks_skipped": counters["tasks_skipped"],
	}
