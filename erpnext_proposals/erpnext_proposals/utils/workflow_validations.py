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
	if doc.is_new():
		return

	old_state = doc.get_value_before_save("workflow_state") or "Borrador"
	new_state = doc.workflow_state or "Borrador"

	if old_state == new_state:
		return  # regular save, not a workflow transition

	_on_workflow_transition(doc, old_state, new_state)


def _on_workflow_transition(doc, old_state: str, new_state: str):
	"""Dispatch validation and traceability logic based on the state transition."""

	# Defensa en profundidad (invariante de producto): una propuesta ya submitted+congelada no puede avanzar
	# por workflow si su economía congelada está incompleta (corrupción/regresión). Misma validación canónica
	# que el submit y el contrato económico. Se EXCLUYE la transición Borrador→En Revisión: es la que
	# SUBMIT+congela (Frappe fija docstatus=1 ANTES de validar, y el freeze corre en esta misma transición y
	# en before_submit); esa ruta la valida `on_quotation_before_submit` DESPUÉS del freeze.
	if doc.docstatus == 1 and not (old_state == "Borrador" and new_state == "En Revision"):
		from erpnext_proposals.erpnext_proposals.utils.quotation import assert_economic_snapshot_complete

		assert_economic_snapshot_complete(doc)

	# Borrador → En Revision: validate, warn, FREEZE proposal and attach PDFs
	# Note: Rechazada → Borrador is impossible at doc level since Rechazada has
	# doc_status=1. Frappe blocks all transitions from submitted to draft natively.
	if old_state == "Borrador" and new_state == "En Revision":
		_validate_blocking(doc)
		_warn_non_blocking(doc)
		from erpnext_proposals.erpnext_proposals.utils.quotation import (
			attach_proposal_pdfs,
			freeze_proposal,
		)

		freeze_proposal(doc)  # hard-fails if snapshot cannot be created
		attach_proposal_pdfs(doc)  # non-blocking, warns if PDF fails
		return

	# En Revision → Aprobada or Rechazada: fill reviewer traceability
	if old_state == "En Revision" and new_state in ("Aprobada", "Rechazada"):
		_fill_traceability(doc, new_state)
		return

	# → Ganada: handoff operativo (issue #39, Fase 1). La DETECCIÓN de la transición ocurre aquí (en
	# validate), pero la ACCIÓN (crear Project) se DIFIERE con enqueue_after_commit=True para no producir
	# efectos secundarios antes de persistir la transición ni revertir `Ganada` si el Project falla.
	if new_state == "Ganada":
		# Acciones INDEPENDIENTES (cada una con su propio toggle y su propio job): un fallo de una no
		# impide la otra. No se encadena la notificación al resultado de la creación del Project.
		_maybe_enqueue_auto_project(doc)
		_maybe_enqueue_won_notification(doc)
		return

	# Aprobada → Enviada al Cliente: optionally add future logic here


def _maybe_enqueue_auto_project(doc) -> None:
	"""Issue #39, Fase 1: si la Company de la Quotation tiene ``auto_create_project_on_won`` activo, encola
	la creación automática del Project **después del commit** (``enqueue_after_commit=True``) — nunca dentro
	de ``validate``. Resolución estricta por Company (sin fallback global): si no hay ``Proposal Settings``
	de esa Company o el toggle está OFF, no hace nada. El job corre como el usuario que dispara la transición
	(``frappe.enqueue`` captura ``frappe.session.user``): sin Administrator ni elevación de privilegios."""
	# Exclusión ESTRUCTURAL de addendas: una addenda nunca crea un Project, ni siquiera con el toggle ON.
	# `auto_create_project_on_won` aplica únicamente a propuestas normales; para addendas la aplicación al
	# Project raíz es explícita (PMO → apply_addendum_to_project). No existe un segundo toggle de addenda.
	from erpnext_proposals.erpnext_proposals.utils.addendum import is_addendum_group

	if is_addendum_group(doc.get("proposal_group")):
		return
	company = doc.get("company")
	if not company:
		return
	settings = frappe.db.get_value("Proposal Settings", {"company": company}, "name")
	if not settings:
		return
	if not frappe.db.get_value("Proposal Settings", settings, "auto_create_project_on_won"):
		return
	frappe.enqueue(
		"erpnext_proposals.erpnext_proposals.utils.project.auto_create_project_on_won",
		quotation_name=doc.name,
		enqueue_after_commit=True,
		queue="short",
		job_name=f"auto_create_project_on_won::{doc.name}",
	)


def _maybe_enqueue_won_notification(doc) -> None:
	"""Issue #39, Fase 1 (2ª acción): si la Company tiene ``send_won_notification_email`` activo y un correo
	destino configurado, encola el envío **después del commit** — nunca en ``validate``. Independiente de la
	creación del Project. Idempotencia por gating de transición (esta rama solo corre en la transición real a
	``Ganada``) + dedup nativo (``job_id`` + ``deduplicate=True``): evita correos duplicados por reintentos
	técnicos sin DocType/estado/log propio. Si el toggle está ON pero falta el correo (config inválida), no
	envía. El job corre como el usuario que dispara la transición (``frappe.enqueue`` captura la sesión)."""
	company = doc.get("company")
	if not company:
		return
	s = frappe.db.get_value(
		"Proposal Settings",
		{"company": company},
		["send_won_notification_email", "won_notification_email"],
		as_dict=True,
	)
	if not s or not s.send_won_notification_email or not s.won_notification_email:
		return
	frappe.enqueue(
		"erpnext_proposals.erpnext_proposals.utils.won_notification.send_won_notification_email",
		quotation_name=doc.name,
		enqueue_after_commit=True,
		queue="short",
		job_id=f"won_notification::{doc.name}",
		deduplicate=True,
	)


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
	from erpnext_proposals.erpnext_proposals.utils.cost_matrix import get_designation_cost

	# Filas costables = las mismas que costea el reporte (vendibles O internas de costo).
	scope_rows = [r for r in doc.quotation_scope_items if r.include_in_proposal or r.is_internal_cost_task]

	# Costo laboral incompleto = filas SIN tarifa resoluble. `Activity Type` NO es requisito: el motor
	# (`get_designation_cost`) resuelve por tarifa específica (Designation + Activity Type), por tarifa
	# GENERAL de la Designation (`is_general_rate=1`) o por Activity Type. Solo se marca incompleto cuando
	# ninguna fuente resuelve una tarifa (`sin_datos` → 0). No se exige Activity Type.
	missing_rate = sum(
		1 for r in scope_rows if not flt(get_designation_cost(r.designation, r.activity_type)[0])
	)

	company_currency = (
		frappe.db.get_value("Company", doc.company, "default_currency") if doc.company else None
	)

	msgs = []
	if missing_rate:
		msgs.append(
			_(
				"{0} tarea(s) sin tarifa de costo resoluble (Designation sin tarifa) — costo laboral incompleto."
			).format(missing_rate)
		)
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
	"""Fill reviewer/approver fields when transitioning to Aprobada or Rechazada.

	Uses frappe.db.set_value to ensure the fields are written directly to DB.
	This bypasses any submitted-doc field restriction in Frappe's save pipeline.
	"""
	user = frappe.session.user
	now = now_datetime()

	updates = {
		"proposal_reviewed_by": user,
		"proposal_reviewed_on": now,
	}

	if new_state == "Aprobada":
		updates["proposal_approved_by"] = user
		updates["proposal_approved_on"] = now

	frappe.db.set_value("Quotation", doc.name, updates, update_modified=False)

	# Keep in-memory doc in sync
	doc.proposal_reviewed_by = user
	doc.proposal_reviewed_on = now
	if new_state == "Aprobada":
		doc.proposal_approved_by = user
		doc.proposal_approved_on = now
