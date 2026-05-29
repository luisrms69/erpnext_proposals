import frappe
from frappe import _

from erpnext_proposals.erpnext_proposals.utils.permissions import assert_can_manage_proposals


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

	scope_rows = [r for r in quotation.quotation_scope_items if r.include_in_proposal]
	if not scope_rows:
		frappe.throw(_("La Cotización no tiene Scope Items con 'Include in Proposal' activo."))

	# Idempotency: reuse if already created
	if quotation.proposal_project and frappe.db.exists("Project", quotation.proposal_project):
		project = frappe.get_doc("Project", quotation.proposal_project)
	else:
		customer = quotation.party_name
		customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer

		project_name = quotation.proposal_title or f"{customer_name} — {quotation.proposal_group}"

		# Recovery: reuse if project exists but reference wasn't saved (partial failure)
		if frappe.db.exists("Project", project_name):
			project = frappe.get_doc("Project", project_name)
		else:
			project = frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": project_name,
					"customer": customer,
					"cost_center": quotation.proposal_cost_center or None,
					"expected_start_date": quotation.transaction_date,
					"status": "Open",
				}
			)
			project.insert(ignore_permissions=True)

		# Store reference on Quotation (allow_on_submit=1 on the field)
		frappe.db.set_value(
			"Quotation", quotation_name, "proposal_project", project.name, update_modified=False
		)

	# Create Tasks from Quotation Scope Items
	tasks_created = 0
	tasks_skipped = 0

	sorted_rows = sorted(scope_rows, key=lambda r: (r.phase or "", r.sequence or 0, r.idx))

	for row in sorted_rows:
		if row.project_task and frappe.db.exists("Task", row.project_task):
			tasks_skipped += 1
			continue

		subject = f"{row.phase} — {row.title}" if row.phase else (row.title or row.code)

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
				"expected_time": row.estimated_hours or 0,
				"description": "".join(desc_parts),
				"status": "Open",
			}
		)
		task.insert(ignore_permissions=True)
		tasks_created += 1

		frappe.db.set_value(
			"Quotation Scope Item", row.name, "project_task", task.name, update_modified=False
		)

	frappe.db.commit()  # nosemgrep

	return {
		"project": project.name,
		"tasks_created": tasks_created,
		"tasks_skipped": tasks_skipped,
	}
