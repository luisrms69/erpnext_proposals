"""
Proposal versioning for erpnext_proposals.

Design:
- Each version is a new Quotation linked via proposal_group.
- Only one "live" proposal per Proposal Group at any time.
- Versions can only be created via create_new_proposal_version().
- before_insert enforces this: previous_proposal without the internal
  flag always raises an error.
- Lock on Proposal Group (SELECT FOR UPDATE) prevents race conditions.
- No manual commits — Frappe transaction handles atomicity.
"""

import frappe
from frappe import _

from erpnext_proposals.erpnext_proposals.utils.permissions import assert_can_manage_proposals

# ── Dead states — a Quotation in these states is NOT considered live ──────────
_DEAD_STATES = frozenset(("Rechazada", "Cancelada"))


# ── Live-proposal query ───────────────────────────────────────────────────────


def get_live_proposal_for_group(proposal_group: str, exclude: str | None = None) -> str | None:
	"""Return the name of the live Quotation in the group, or None."""
	rows = frappe.db.get_all(
		"Quotation",
		filters={
			"proposal_group": proposal_group,
			"docstatus": ("!=", 2),
			"workflow_state": ("not in", list(_DEAD_STATES)),
			"superseded_by_proposal": ("in", ("", None)),
		},
		fields=["name"],
	)
	for row in rows:
		if row.name != exclude:
			return row.name
	return None


def assert_single_live_proposal_for_group(proposal_group: str, current: str | None = None) -> None:
	"""Raise if another live Quotation exists in the group (other than `current`)."""
	live = get_live_proposal_for_group(proposal_group, exclude=current)
	if live:
		frappe.throw(
			_(
				"Ya existe una propuesta activa en el grupo {0}: {1}. "
				"Solo puede existir una propuesta viva por Proposal Group."
			).format(proposal_group, live)
		)


# ── Version-creation guards ───────────────────────────────────────────────────


def assert_can_create_new_version(old_doc) -> None:
	if old_doc.docstatus != 1:
		frappe.throw(_("Solo se puede versionar desde una Quotation submitted."))
	if old_doc.workflow_state != "Rechazada":
		frappe.throw(_("Nueva versión solo disponible desde estado Rechazada."))
	if old_doc.superseded_by_proposal:
		frappe.throw(_("Esta versión ya fue reemplazada por {0}.").format(old_doc.superseded_by_proposal))
	if not getattr(old_doc, "proposal_group", None):
		frappe.throw(_("La Quotation no tiene Proposal Group asignado."))
	if getattr(old_doc, "proposal_project", None) and frappe.db.exists("Project", old_doc.proposal_project):
		frappe.throw(
			_(
				"La propuesta tiene un Proyecto activo ({0}). "
				"No se puede crear una nueva versión desde una propuesta con Proyecto."
			).format(old_doc.proposal_project)
		)


def assert_can_create_project(doc) -> None:
	if doc.docstatus != 1:
		frappe.throw(_("El Proyecto solo puede crearse desde una Quotation submitted."))
	if doc.workflow_state != "Ganada":
		frappe.throw(_("El Proyecto solo puede crearse desde una propuesta Ganada."))
	if getattr(doc, "superseded_by_proposal", None):
		frappe.throw(
			_("Esta versión fue reemplazada por {0}. Use la versión vigente.").format(
				doc.superseded_by_proposal
			)
		)
	if getattr(doc, "proposal_group", None):
		assert_single_live_proposal_for_group(doc.proposal_group, current=doc.name)
	# proposal_project check intentionally removed: idempotency is handled in
	# project.py (reuses existing project). Superseded versions are already blocked
	# above via superseded_by_proposal. See test_17 and test_ganada_with_existing_project.


# ── Internal helpers ──────────────────────────────────────────────────────────


def _next_version(proposal_group: str) -> int:
	"""Calculate next proposal_version. Must be called inside the quotation lock."""
	result = frappe.db.sql(
		"SELECT COALESCE(MAX(proposal_version), 0) FROM `tabQuotation` WHERE proposal_group = %s",
		proposal_group,
	)
	return (result[0][0] or 0) + 1


def _validate_previous_proposal_basic(doc) -> None:
	if not doc.proposal_group:
		frappe.throw(_("Quotation con previous_proposal debe tener proposal_group asignado."))
	if not frappe.db.exists("Quotation", doc.previous_proposal):
		frappe.throw(_("La Quotation anterior {0} no existe.").format(doc.previous_proposal))
	if not doc.proposal_version:
		frappe.throw(_("proposal_version es requerido cuando se especifica previous_proposal."))


def _validate_previous_proposal_under_lock(doc) -> None:
	"""Re-read previous_proposal from DB inside the Proposal Group lock."""
	prev = frappe.db.get_value(
		"Quotation",
		doc.previous_proposal,
		["proposal_group", "workflow_state", "docstatus", "superseded_by_proposal"],
		as_dict=True,
	)
	if prev.proposal_group != doc.proposal_group:
		frappe.throw(
			_("La Quotation anterior {0} pertenece al grupo {1}, no a {2}.").format(
				doc.previous_proposal, prev.proposal_group, doc.proposal_group
			)
		)
	if prev.workflow_state != "Rechazada":
		frappe.throw(
			_("La Quotation anterior debe estar Rechazada. Estado: {0}.").format(prev.workflow_state)
		)
	if prev.superseded_by_proposal:
		frappe.throw(
			_("La Quotation {0} ya fue reemplazada por {1}.").format(
				doc.previous_proposal, prev.superseded_by_proposal
			)
		)


def _validate_proposal_version_sequential(doc) -> None:
	"""Verify proposal_version == max(group) + 1. Must be inside lock."""
	result = frappe.db.sql(
		"SELECT COALESCE(MAX(proposal_version), 0) FROM `tabQuotation` WHERE proposal_group = %s",
		doc.proposal_group,
	)
	max_v = result[0][0] or 0
	expected = max_v + 1
	if doc.proposal_version != expected:
		frappe.throw(
			_("proposal_version debe ser {0} (máximo actual del grupo: {1}).").format(expected, max_v)
		)


# ── Copy helpers — explicit field lists, no ignored mandatory ────────────────


def _copy_item(item) -> dict:
	return {
		"item_code": item.item_code,
		"item_name": item.item_name,
		"description": item.description,
		"qty": item.qty,
		"uom": item.uom,
		"rate": item.rate,
		"price_list_rate": item.price_list_rate,
		"discount_percentage": item.discount_percentage,
		"item_tax_template": item.item_tax_template,
		"warehouse": item.warehouse,
		# Contenido general congelado del Item: se conserva de la versión anterior (línea Quotation Item),
		# NUNCA se relee el Item maestro al versionar.
		"proposal_methodology": item.get("proposal_methodology"),
		"proposal_expected_result": item.get("proposal_expected_result"),
		"proposal_scope_limit": item.get("proposal_scope_limit"),
	}


def _copy_tax(tax) -> dict:
	return {
		"charge_type": tax.charge_type,
		"account_head": tax.account_head,
		"description": tax.description,
		"rate": tax.rate,
	}


def _is_automatic_single_row(sched) -> bool:
	"""True si el Payment Schedule es (a lo sumo) la fila automática estándar del 100% sin
	payment_term ni descripción (la que ERPNext genera por defecto sin Payment Terms Template)."""
	if not sched:
		return True
	if len(sched) > 1:
		return False
	row = sched[0]
	return not row.get("payment_term") and not (row.get("description") or "").strip()


def _resolve_new_version_payment(old):
	"""Determina (payment_terms_template, payment_schedule) para la nueva revisión SIN copiar
	due_dates inválidos del documento anterior. Comportamiento nativo de ERPNext:

	- Con Payment Terms Template → se conserva el template y el schedule se deja vacío para que
	  ERPNext lo regenere desde la nueva transaction_date (importes desde el nuevo total).
	- Solo con la fila automática estándar del 100% (sin término ni descripción) → schedule vacío
	  (ERPNext regenera la fila con la fecha válida de la revisión).
	- Con un calendario MANUAL significativo → NO se falsean condiciones: se detiene con un mensaje
	  claro para que el usuario decida (Payment Terms Template o ajuste manual con fechas válidas).
	"""
	sched = old.payment_schedule or []
	if old.get("payment_terms_template"):
		return old.payment_terms_template, []
	if _is_automatic_single_row(sched):
		return None, []
	frappe.throw(
		_(
			"La propuesta {0} tiene un calendario de pagos capturado manualmente ({1} fila(s)). "
			"Para no falsear sus condiciones comerciales, la revisión no se crea automáticamente. "
			"Define un Payment Terms Template o ajusta el calendario con fechas válidas para la nueva "
			"revisión y vuelve a intentar."
		).format(old.name, len(sched))
	)


def _copy_scope_item(scope) -> dict:
	return {
		"scope_item": scope.scope_item,  # master catalog ref — needed to deduplicate on validate
		"item_code": scope.item_code,  # quotation item link — needed for catalog matching
		"auto_generated": scope.auto_generated,
		"title": scope.title,
		"code": scope.code,
		"phase": scope.phase,
		"sequence": scope.sequence,
		"description": scope.description,
		"deliverable": scope.deliverable,
		"activity_type": scope.activity_type,
		"designation": scope.designation,
		"estimated_hours": scope.estimated_hours,
		"include_in_proposal": scope.include_in_proposal,
		# cost_per_hour, total_cost, project_task NOT copied — recalculated on review
	}


# ── Public API ────────────────────────────────────────────────────────────────


@frappe.whitelist()
def create_new_proposal_version(quotation_name: str, reason: str, summary: str = "") -> str:
	"""
	Create a new proposal version from a Rejected submitted Quotation.

	Atomicity: insert + superseded_by_proposal update happen in the same
	Frappe transaction. No manual commit. Lock on Proposal Group prevents
	race conditions.
	"""
	assert_can_manage_proposals()

	if not reason:
		frappe.throw(_("El motivo de revisión es obligatorio."))

	old = frappe.get_doc("Quotation", quotation_name)
	assert_can_create_new_version(old)

	# Lock the old Quotation row — serializes concurrent version attempts
	# on the same Quotation. After acquiring the lock, revalidate state.
	frappe.db.sql(
		"SELECT name FROM `tabQuotation` WHERE name = %s FOR UPDATE",
		old.name,
	)

	# Revalidate inside lock with fresh DB data
	old.reload()
	if old.superseded_by_proposal:
		frappe.throw(
			_("Una nueva versión fue creada concurrentemente: {0}.").format(old.superseded_by_proposal)
		)
	assert_single_live_proposal_for_group(old.proposal_group, current=old.name)

	new_version_number = _next_version(old.proposal_group)

	# La nueva versión HEREDA el formato efectivo anterior como override editable (proposal_print_format).
	# El formato congelado (proposal_effective_print_format) NO se copia (no_copy=1): se recongela en Borrador.
	from erpnext_proposals.erpnext_proposals.utils.print_format import resolve_commercial_print_format

	inherited_print_format = resolve_commercial_print_format(old)

	# Calendario de pagos: NUNCA copiar due_dates del documento anterior (serían inválidos contra la
	# nueva fecha). Se regenera con el comportamiento nativo de ERPNext desde la nueva transaction_date.
	pt_template, pay_schedule = _resolve_new_version_payment(old)

	new_doc = frappe.get_doc(
		{
			"doctype": "Quotation",
			"quotation_to": old.quotation_to,
			"party_name": old.party_name,
			"company": old.company,
			"currency": old.currency,
			"selling_price_list": old.selling_price_list,
			"transaction_date": frappe.utils.today(),
			"valid_till": None,
			"proposal_group": old.proposal_group,
			"proposal_version": new_version_number,
			"previous_proposal": old.name,
			"proposal_template": old.proposal_template,
			"proposal_title": old.proposal_title,
			"proposal_cost_center": old.proposal_cost_center,
			"proposal_print_format": inherited_print_format,
			"proposal_revision_reason": reason,
			"proposal_revision_summary": summary,
			"items": [_copy_item(i) for i in old.items],
			"taxes": [_copy_tax(t) for t in old.taxes],
			"payment_terms_template": pt_template,
			"payment_schedule": pay_schedule,
			"quotation_scope_items": [_copy_scope_item(s) for s in old.quotation_scope_items],
		}
	)

	# Internal flag: allows before_insert to accept previous_proposal.
	# frappe.flags is Python-only, not persisted, not settable via REST API.
	new_doc.flags.from_proposal_versioning = True
	new_doc.flags.skip_scope_generation = True  # scope already copied — don't regenerate

	# No ignore_mandatory — all mandatory fields must be explicitly in the dict.
	new_doc.insert(ignore_permissions=True)

	# Update previous version — same Frappe transaction, no manual commit.
	frappe.db.set_value(
		"Quotation",
		old.name,
		"superseded_by_proposal",
		new_doc.name,
		update_modified=False,
	)

	return new_doc.name


def get_version_history(proposal_group: str) -> list:
	"""Return all Quotation versions for a Proposal Group, ordered by version."""
	return frappe.db.get_all(
		"Quotation",
		filters={"proposal_group": proposal_group},
		fields=[
			"name",
			"proposal_version",
			"workflow_state",
			"docstatus",
			"transaction_date",
			"proposal_revision_reason",
			"superseded_by_proposal",
			"proposal_project",
			"grand_total",
			"currency",
		],
		order_by="proposal_version asc",
	)
