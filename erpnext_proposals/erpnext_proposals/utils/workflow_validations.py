import frappe
from frappe import _
from frappe.utils import flt, now_datetime


def before_workflow_action(doc, method=None):
	"""
	Validates Quotation before any workflow transition.
	Blocking: proposal_template, proposal_cost_center, net_total > 0.
	Warnings only: missing costs, activity_type, margin, currency.
	"""
	_validate_blocking(doc)
	_warn_non_blocking(doc)
	_fill_traceability(doc)


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


def _fill_traceability(doc):
	"""Fill review/approval traceability fields based on the workflow action being executed.

	Frappe sets doc.workflow_action before firing before_workflow_action.
	- "Aprobar" or "Rechazar": fill proposal_reviewed_by / proposal_reviewed_on.
	- "Aprobar" only: also fill proposal_approved_by / proposal_approved_on.
	"""
	action = getattr(doc, "workflow_action", None)
	if not action:
		return

	user = frappe.session.user
	now = now_datetime()

	if action in ("Aprobar", "Rechazar"):
		doc.proposal_reviewed_by = user
		doc.proposal_reviewed_on = now

	if action == "Aprobar":
		doc.proposal_approved_by = user
		doc.proposal_approved_on = now
