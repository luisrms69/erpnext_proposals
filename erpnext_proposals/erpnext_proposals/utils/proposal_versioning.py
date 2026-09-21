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


# ── Copia metadata-driven: heredar por defecto todo el estado comercial ──────────
#
# Principio (regla de negocio): una nueva versión CONSERVA por defecto todo el avance comercial de la
# anterior. Solo se excluye/reset/recalcula lo que tenga una razón demostrable por pertenecer a:
# identidad del nuevo documento · workflow · cadena de versiones · artefactos downstream · snapshots/
# frozen · cálculos técnicos derivados.
#
# El conjunto a copiar se DERIVA de `frappe.get_meta` (padre + cada child table gestionada): se copia
# cada campo de valor con `no_copy == 0` que NO esté en EXCLUDE[doctype], UNIÓN los FORCE_INCLUDE
# (campos `no_copy=1` que sí queremos), y luego se aplican los TRANSFORM en create_new_proposal_version.
# Así, cualquier campo nuevo (custom o nativo) se hereda por defecto; solo las excepciones se enumeran.

# Campos de framework que nunca se copian (Frappe los gestiona / autoname).
_SYS_EXCLUDE = frozenset(
	{
		"name",
		"owner",
		"creation",
		"modified",
		"modified_by",
		"docstatus",
		"idx",
		"amended_from",
		"naming_series",
		"doctype",
		"parent",
		"parentfield",
		"parenttype",
	}
)

# Tipos de campo sin valor (layout / presentación) — no se copian.
_LAYOUT_FT = frozenset(
	{"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading", "Image"}
)

# EXCLUDE por DocType: campos `no_copy=0` que NO deben heredarse literalmente (con su categoría).
_EXCLUDE = {
	"Quotation": frozenset(
		{
			# cadena de versiones (fijados por TRANSFORM)
			"proposal_version",
			"previous_proposal",
			"superseded_by_proposal",
			"proposal_revision_reason",
			"proposal_revision_summary",
			# workflow / ciclo de vida (nueva Draft)
			"workflow_state",
			"status",
			# artefacto downstream (Proyecto solo tras Ganada)
			"proposal_project",
			# derivados / TRANSFORM
			"transaction_date",
			"proposal_print_format",
			"payment_terms_template",
			"payment_schedule",
			# frozen (ya son no_copy=1; explícitos por claridad)
			"proposal_effective_print_format",
			"proposal_reviewed_by",
			"proposal_reviewed_on",
			"proposal_approved_by",
			"proposal_approved_on",
		}
	),
	# Montos computados por ERPNext al validar (se recalculan; no arrastrar valores viejos).
	"Quotation Item": frozenset(
		{
			"amount",
			"base_amount",
			"base_rate",
			"base_price_list_rate",
			"base_net_rate",
			"base_net_amount",
			"net_rate",
			"net_amount",
			"stock_qty",
			"stock_uom_rate",
		}
	),
	# Filas de impuesto: se heredan los inputs (charge_type/account_head/rate/description/cost_center/
	# included_in_print_rate/row_id y tax_amount para charge_type=Actual). Los montos base/totales los
	# recalcula ERPNext (calculate_taxes_and_totals) al validar.
	"Sales Taxes and Charges": frozenset(
		{
			"total",
			"tax_amount_after_discount_amount",
			"base_tax_amount",
			"base_total",
			"base_tax_amount_after_discount_amount",
			"net_amount",
			"base_net_amount",
			"account_currency",
		}
	),
	# Scope Item: se excluyen calculados/congelados (re-resueltos en revisión), downstream (project_task)
	# y procedencia (source_type/source_row, re-derivada al validar/generar).
	"Quotation Scope Item": frozenset(
		{
			"costing_rate",
			"rate_source",
			"rate_locked",
			"rate_locked_on",
			"project_task",
			"source_type",
			"source_row",
		}
	),
	# Required Item: snapshots congelados (ADR-0019 §7.4) — se re-congelan al re-formalizar. NOTA: estos
	# campos NO están marcados no_copy=1 en el DocType, por eso la deny-list explícita es imprescindible.
	"Proposal Required Item": frozenset(
		{
			"frozen_cost_rate",
			"frozen_cost_source",
			"cost_locked",
			"economic_behavior",
			"billing_interval",
			"billing_interval_count",
		}
	),
	# Payment Schedule (caso manual): se heredan los inputs; los base/derivados los recalcula ERPNext.
	"Payment Schedule": frozenset(
		{
			"base_payment_amount",
			"base_paid_amount",
			"paid_amount",
			"outstanding",
			"base_outstanding",
			"discounted_amount",
		}
	),
	"Proposal Optional Section": frozenset(),
}

# FORCE_INCLUDE: campos `no_copy=1` que SÍ se copian literalmente a la nueva versión.
# Flujo nuevo: la narrativa se hereda como child table (`proposal_sections`, ver _CHILD_TABLES), NO
# como `proposal_sections_snapshot` JSON. El snapshot legacy no se force-copia; una versión creada desde
# una Rechazada histórica que SOLO tiene snapshot se convierte una vez a filas (ver utils.quotation
# _convert_legacy_snapshot_to_rows, invocado en este flujo).
_FORCE_INCLUDE = {}

# Child tables gestionadas por herencia directa (parent fieldname -> child DocType).
# `payment_schedule` NO va aquí: lo resuelve _resolve_new_version_payment (template vs manual).
_CHILD_TABLES = {
	"items": "Quotation Item",
	"taxes": "Sales Taxes and Charges",
	"quotation_scope_items": "Quotation Scope Item",
	"required_items": "Proposal Required Item",
	"proposal_optional_sections": "Proposal Optional Section",
	# Narrativa materializada: se copia como datos normales de la nueva versión (independiente de
	# maestros). El guardado de la versión no re-materializa (skip_scope_generation en validate).
	"proposal_sections": "Proposal Quotation Section",
}


def _copy_fields(source, doctype: str, skip_tables: bool) -> dict:
	"""Construye el dict de campos heredados de `source` para `doctype` según la regla metadata-driven."""
	meta = frappe.get_meta(doctype)
	exclude = _EXCLUDE.get(doctype, frozenset())
	force = _FORCE_INCLUDE.get(doctype, frozenset())
	out = {}
	for df in meta.fields:
		fn = df.fieldname
		if df.fieldtype in _LAYOUT_FT or fn in _SYS_EXCLUDE:
			continue
		if skip_tables and df.fieldtype in ("Table", "Table MultiSelect"):
			continue  # las child tables se construyen aparte
		inherit = (not df.no_copy and fn not in exclude) or (fn in force)
		if inherit:
			out[fn] = source.get(fn)
	return out


def _copy_row(child_doctype: str, row) -> dict:
	"""Fila hija heredada (mismo criterio: no_copy=0 y no en EXCLUDE, mas FORCE_INCLUDE)."""
	return _copy_fields(row, child_doctype, skip_tables=True)


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
	"""Determina (payment_terms_template, payment_schedule) preservando el trabajo comercial.

	- Con Payment Terms Template → se conserva el template y el schedule se deja vacío para que ERPNext
	  regenere lo estrictamente derivado (due_dates/importes) desde la nueva transaction_date.
	- Solo la fila automática estándar del 100% (sin término ni descripción) → schedule vacío (ERPNext
	  regenera la fila).
	- Calendario MANUAL significativo → SE PRESERVAN las filas (payment_term, descripción, invoice_portion,
	  payment_amount, due_date, mode_of_payment, descuentos). Solo los campos base/derivados se recalculan.
	  NO se descarta el trabajo comercial ni se detiene con un throw.
	"""
	sched = old.payment_schedule or []
	if old.get("payment_terms_template"):
		return old.payment_terms_template, []
	if _is_automatic_single_row(sched):
		return None, []
	return None, [_copy_row("Payment Schedule", r) for r in sched]


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

	# Calendario de pagos: se preserva el trabajo comercial (template → regenera derivados; manual →
	# hereda las filas). Ver _resolve_new_version_payment.
	pt_template, pay_schedule = _resolve_new_version_payment(old)

	# ── Herencia metadata-driven del estado comercial (padre + child tables) ──
	values = _copy_fields(old, "Quotation", skip_tables=True)
	for parent_field, child_doctype in _CHILD_TABLES.items():
		values[parent_field] = [_copy_row(child_doctype, r) for r in (old.get(parent_field) or [])]

	# B5: compatibilidad puntual de ENTRADA. Una Rechazada legacy que solo tiene
	# `proposal_sections_snapshot` (sin filas materializadas) se convierte UNA VEZ a filas
	# `proposal_sections` para el nuevo Draft. Los históricos no se tocan; el nuevo Draft renderiza
	# solo desde filas (sin renderer legacy paralelo).
	if not values.get("proposal_sections") and (old.get("proposal_sections_snapshot") or "").strip():
		from erpnext_proposals.erpnext_proposals.utils.quotation import _convert_legacy_snapshot_to_rows

		values["proposal_sections"] = _convert_legacy_snapshot_to_rows(old.proposal_sections_snapshot)

	# ── TRANSFORM: identidad del nuevo documento · cadena de versiones · workflow · downstream ──
	values.update(
		{
			"doctype": "Quotation",
			"transaction_date": frappe.utils.today(),
			"workflow_state": "Borrador",
			"proposal_version": new_version_number,
			"previous_proposal": old.name,
			"superseded_by_proposal": None,
			"proposal_project": None,
			"proposal_revision_reason": reason,
			"proposal_revision_summary": summary,
			# Formato efectivo anterior heredado como override editable; el congelado se recongela.
			"proposal_print_format": inherited_print_format,
			# Pagos: template heredado (derivados regenerados) o filas manuales preservadas.
			"payment_terms_template": pt_template,
			"payment_schedule": pay_schedule,
		}
	)

	# valid_till: heredado LITERAL (por _copy_fields) siempre que siga vigente contra la nueva fecha.
	# ERPNext prohíbe nativamente `valid_till < transaction_date` en CADA save, incluido Borrador
	# (Quotation.validate_valid_till). Si la fecha heredada ya venció respecto de HOY, ERPNext impediría
	# crear la nueva Draft; para no romper el versionado se deja en blanco (el usuario la recaptura).
	# NOTA: desviación acotada respecto de "heredar literal SIEMPRE", forzada por la validación nativa.
	_vt = old.get("valid_till")
	if _vt and frappe.utils.getdate(_vt) < frappe.utils.getdate(values["transaction_date"]):
		values["valid_till"] = None

	new_doc = frappe.get_doc(values)

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
