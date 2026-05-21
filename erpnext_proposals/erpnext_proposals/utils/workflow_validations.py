import frappe
from frappe import _
from frappe.utils import flt, now_datetime


def on_quotation_validate_workflow(doc, method=None):
	"""
	Handles workflow-related validation and traceability for Quotation.

	Called on every validate (Frappe v16 does not fire before_workflow_action
	server-side — it is a JavaScript-only event). State transition is detected
	by comparing doc.workflow_state against the persisted value.
	"""
	frappe.logger("proposals").debug(
		f"on_quotation_validate_workflow called: doc={doc.name} "
		f"is_new={doc.is_new()} workflow_state={doc.workflow_state} "
		f"before_save={doc.get_value_before_save('workflow_state')}"
	)

	if doc.is_new():
		return

	old_state = doc.get_value_before_save("workflow_state") or "Borrador"
	new_state = doc.workflow_state or "Borrador"

	frappe.logger("proposals").debug(f"old={old_state!r} new={new_state!r}")

	if old_state == new_state:
		return  # regular save, not a workflow transition

	_on_workflow_transition(doc, old_state, new_state)


def _on_workflow_transition(doc, old_state: str, new_state: str):
	"""Dispatch validation and traceability logic based on the state transition."""

	# Borrador → En Revision: validate required fields and warn on cost gaps
	if old_state == "Borrador" and new_state == "En Revision":
		_validate_blocking(doc)
		_warn_non_blocking(doc)
		return

	# En Revision → Aprobada or Rechazada: fill reviewer traceability
	if old_state == "En Revision" and new_state in ("Aprobada", "Rechazada"):
		_fill_traceability(doc, new_state)
		return

	# Rechazada → Borrador: no special action (user is revising)
	# Aprobada → Enviada al Cliente: optionally add future logic here


def _validate_blocking(doc):
	errors = []

	if not doc.proposal_template:
		errors.append(_("La Cotización debe tener un Proposal Template asignado."))

	if not doc.proposal_cost_center:
		errors.append(_("La Cotización debe tener un Proposal Cost Center asignado."))

	if not flt(doc.net_total):
		errors.append(_("La venta neta no puede ser cero."))

	if errors:
		frappe.throw("<br>".join(errors), title=_("No se puede avanzar en el flujo"))


def _warn_non_blocking(doc):
	scope_rows = [r for r in doc.quotation_scope_items if r.include_in_proposal]

	missing_activity = sum(1 for r in scope_rows if not r.activity_type)
	missing_rate = 0
	for r in scope_rows:
		if r.activity_type:
			rate = frappe.db.get_value("Activity Type", r.activity_type, "costing_rate") or 0
			if not rate:
				missing_rate += 1

	company_currency = (
		frappe.db.get_value("Company", doc.company, "default_currency") if doc.company else None
	)

	msgs = []
	if missing_activity:
		msgs.append(_("{0} tarea(s) sin activity_type — costo laboral incompleto.").format(missing_activity))
	if missing_rate:
		msgs.append(_("{0} tarea(s) sin costing_rate — costo laboral incompleto.").format(missing_rate))
	if company_currency and doc.currency != company_currency:
		msgs.append(
			_("Moneda de Quotation ({0}) difiere de moneda base ({1}).").format(
				doc.currency, company_currency
			)
		)

	if msgs:
		frappe.msgprint(
			"<br>".join(msgs),
			title=_("Advertencias de costeo"),
			indicator="orange",
			alert=True,
		)


def _fill_traceability(doc, new_state: str):
	"""Fill reviewer/approver fields when transitioning to Aprobada or Rechazada."""
	user = frappe.session.user
	now = now_datetime()

	doc.proposal_reviewed_by = user
	doc.proposal_reviewed_on = now

	if new_state == "Aprobada":
		doc.proposal_approved_by = user
		doc.proposal_approved_on = now
