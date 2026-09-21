"""Reparación CANÓNICA de snapshots económicos LEGACY (compatibilidad histórica).

Contexto: el snapshot económico por línea (costo externo congelado + comportamiento económico) apareció
en v0.17.0 (ADR-0017) / v0.18.0 (ADR-0018) y el guard global ``assert_economic_snapshot_complete`` se
endureció en v0.23.0. Las Quotations formalizadas ANTES de ese modelo no tienen esos campos y hoy quedan
bloqueadas al avanzar el workflow (p. ej. Enviada al Cliente → Ganada) o al crear Project.

Este módulo NO desactiva el guard ni hace bypass. Repara, de forma explícita, fail-closed, idempotente y
auditable, UNA Quotation histórica identificada por nombre, escribiendo el snapshot con la semántica
EQUIVALENTE al comportamiento pre-modelo: sin costo externo del modelo nuevo (rate 0, source
``legacy_pre_economic_model``, locked) y comportamiento ``one_time`` sin recurrencia. NUNCA reconstruye el
pasado desde datos vivos (Item Price / last_purchase / Proposal Settings actuales) ni hace backfill masivo.
"""

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

LEGACY_SOURCE = "legacy_pre_economic_model"

# Marcadores OBJETIVOS del modelo económico: Custom Fields introducidos por ADR-0017 / ADR-0018. Su fecha
# `creation` EN ESTE SITE es la señal canónica de "cuándo empezó a existir el modelo económico aquí". Una
# Quotation creada ANTES es demostrablemente pre-modelo (legacy); una creada DESPUÉS con snapshot vacío es
# posible corrupción/regresión, NO legacy. No es una fecha inventada: se lee del propio metadata del site.
_ECON_MODEL_MARKERS = (
	"Quotation Item-proposal_cost_locked",  # ADR-0017 (costo externo congelado)
	"Quotation Item-proposal_economic_behavior",  # ADR-0018 (comportamiento económico)
)


def legacy_cutoff() -> tuple:
	"""``(cutoff_datetime, marker_field)`` = la creación MÁS TEMPRANA de los Custom Fields del modelo
	económico en este site (= introducción del modelo). ``(None, None)`` si la señal no está disponible."""
	best = None
	for name in _ECON_MODEL_MARKERS:
		created = frappe.db.get_value("Custom Field", name, "creation")
		if created and (best is None or get_datetime(created) < get_datetime(best[0])):
			best = (created, name)
	return best if best else (None, None)


# Campos económicos por línea VENDIDA (Quotation Item) y su equivalente en Required Item.
# El guard (assert_economic_snapshot_complete) exige, como mínimo: en vendidas
# proposal_cost_locked + proposal_economic_behavior; en required cost_locked + economic_behavior.
_ITEM_KEY = ("proposal_cost_locked", "proposal_economic_behavior")
_ITEM_ALL = (
	"proposal_cost_locked",
	"proposal_economic_behavior",
	"proposal_frozen_cost_rate",
	"proposal_frozen_cost_source",
	"proposal_billing_interval",
	"proposal_billing_interval_count",
)
_REQ_KEY = ("cost_locked", "economic_behavior")
_REQ_ALL = (
	"cost_locked",
	"economic_behavior",
	"frozen_cost_rate",
	"frozen_cost_source",
	"billing_interval",
	"billing_interval_count",
)

# Valores de reparación LEGACY (equivalencia histórica: sin costo externo del modelo nuevo, one_time).
_ITEM_REPAIR = {
	"proposal_frozen_cost_rate": 0,
	"proposal_frozen_cost_source": LEGACY_SOURCE,
	"proposal_cost_locked": 1,
	"proposal_economic_behavior": "one_time",
	"proposal_billing_interval": "",
	"proposal_billing_interval_count": 0,
}
_REQ_REPAIR = {
	"frozen_cost_rate": 0,
	"frozen_cost_source": LEGACY_SOURCE,
	"cost_locked": 1,
	"economic_behavior": "one_time",
	"billing_interval": "",
	"billing_interval_count": 0,
}


def _is_set(value) -> bool:
	"""Un campo económico se considera 'presente' si tiene contenido significativo."""
	if value in (None, "", 0, "0"):
		return False
	return True


def _econ_state(row, key_fields: tuple, all_fields: tuple) -> str:
	"""Estado del snapshot económico de una línea:

	- ``complete``: presentes los campos que exige el guard (locked + behavior).
	- ``empty``: NINGUNO de los campos económicos del modelo nuevo está presente (línea legacy pura).
	- ``partial``: combinación intermedia → AMBIGUA (no se interpreta; se aborta la reparación).
	"""
	if all(_is_set(row.get(f)) for f in key_fields):
		return "complete"
	if not any(_is_set(row.get(f)) for f in all_fields):
		return "empty"
	return "partial"


def _plan_rows(rows, key_fields, all_fields, repair_values, doctype_label, id_field):
	"""Devuelve (to_repair, blockers) para una colección de líneas (items o required_items)."""
	to_repair, blockers = [], []
	for row in rows or []:
		state = _econ_state(row, key_fields, all_fields)
		ident = row.get(id_field)
		if state == "complete":
			continue
		if state == "partial":
			present = {f: row.get(f) for f in all_fields if _is_set(row.get(f))}
			blockers.append(
				f"{doctype_label} '{ident}': snapshot económico PARCIAL/ambiguo {present} — no se repara "
				"(requiere revisión manual, no se infiere)"
			)
			continue
		# empty → legacy puro → reparar
		to_repair.append(
			{
				"row": row,
				"ident": ident,
				"changes": [{"field": f, "old": row.get(f), "new": v} for f, v in repair_values.items()],
			}
		)
	return to_repair, blockers


@frappe.whitelist()
def repair_legacy_economic_snapshot(quotation_name: str, dry_run: bool | str = True) -> dict:
	"""Repara el snapshot económico legacy de UNA Quotation histórica (por nombre). fail-closed.

	Uso:
	    bench --site <site> execute erpnext_proposals.erpnext_proposals.utils.legacy_repair.repair_legacy_economic_snapshot \\
	        --kwargs "{'quotation_name': 'SAL-QTN-2026-00001', 'dry_run': True}"

	Con ``dry_run=True`` (por defecto) solo reporta el plan; con ``dry_run=False`` persiste atómicamente y
	deja un Comment de trazabilidad. NUNCA sobrescribe snapshots existentes; aborta ante estados parciales/
	ambiguos o Scope Items costables sin ``rate_locked`` (no inventa costo laboral histórico).
	"""
	frappe.only_for("System Manager")
	if isinstance(dry_run, str):
		dry_run = frappe.utils.sbool(dry_run)
	dry_run = bool(dry_run)

	# ── Precondiciones fail-closed ──
	if not frappe.db.exists("Quotation", quotation_name):
		frappe.throw(_("La Quotation '{0}' no existe.").format(quotation_name))
	doc = frappe.get_doc("Quotation", quotation_name)
	if doc.docstatus != 1:
		frappe.throw(
			_(
				"La Quotation '{0}' no está sometida (docstatus={1}); la reparación legacy solo aplica a "
				"propuestas formalizadas."
			).format(quotation_name, doc.docstatus)
		)
	if not doc.get("proposal_template"):
		frappe.throw(
			_(
				"La Quotation '{0}' no es una propuesta formal (sin proposal_template); no lleva snapshot "
				"económico."
			).format(quotation_name)
		)

	# ── Elegibilidad LEGACY objetiva (cutoff = introducción del modelo económico en el site) ──
	cutoff, cutoff_field = legacy_cutoff()
	legacy_eligible = bool(cutoff) and get_datetime(doc.creation) < get_datetime(cutoff)

	report = {
		"quotation": doc.name,
		"docstatus": doc.docstatus,
		"creation": str(doc.creation),
		"workflow_state": doc.get("workflow_state"),
		"proposal_template": doc.proposal_template,
		"legacy_cutoff": str(cutoff) if cutoff else None,
		"legacy_cutoff_field": cutoff_field,
		"legacy_eligible": legacy_eligible,
		"dry_run": dry_run,
		"items_to_repair": [],
		"required_to_repair": [],
		"blockers": [],
		"already_complete": False,
		"applied": False,
		"guard_after": None,
	}

	# ── Gate de Scope Items: si alguno costable carece de rate_locked, ABORTAR (no inventar costo laboral) ──
	for s in doc.get("quotation_scope_items") or []:
		if (s.get("include_in_proposal") or s.get("is_internal_cost_task")) and not s.get("rate_locked"):
			report["blockers"].append(
				f"Scope '{s.get('code') or s.get('scope_item')}': sin rate_locked — no se inventa costo "
				"laboral histórico (reparación abortada)"
			)

	# ── Plan de reparación por línea vendida y required ──
	items_plan, item_blk = _plan_rows(
		doc.get("items"), _ITEM_KEY, _ITEM_ALL, _ITEM_REPAIR, "Item", "item_code"
	)
	req_plan, req_blk = _plan_rows(
		doc.get("required_items"), _REQ_KEY, _REQ_ALL, _REQ_REPAIR, "Required", "item"
	)
	report["blockers"] += item_blk + req_blk
	report["items_to_repair"] = [{"item_code": p["ident"], "changes": p["changes"]} for p in items_plan]
	report["required_to_repair"] = [{"item": p["ident"], "changes": p["changes"]} for p in req_plan]

	# ── Gate de ELEGIBILIDAD LEGACY: solo se reparan documentos demostrablemente anteriores al modelo ──
	if items_plan or req_plan:
		if cutoff is None:
			report["blockers"].append(
				"No se pudo establecer el cutoff legacy: los Custom Fields del modelo económico "
				f"({', '.join(_ECON_MODEL_MARKERS)}) no existen en el site. Señal no disponible → abortado."
			)
		elif not legacy_eligible:
			report["blockers"].append(
				f"Quotation NO elegible como legacy: creation {doc.creation} >= cutoff del modelo económico "
				f"{cutoff} (campo {cutoff_field}). Un snapshot vacío en una propuesta POSTERIOR al modelo es "
				"posible CORRUPCIÓN/REGRESIÓN, no legacy: no se repara."
			)

	# ── Abortos ──
	if report["blockers"]:
		report["note"] = "ABORTADO: hay condiciones que no se pueden reparar con seguridad (ver blockers)."
		return report

	if not items_plan and not req_plan:
		# Nada que reparar: o ya está completo, o no hay líneas económicas.
		report["already_complete"] = True
		report["note"] = "Nada que reparar: el snapshot económico ya está completo (idempotente)."
		return report

	# ── Aplicar EN MEMORIA para validar contra el guard canónico ──
	from erpnext_proposals.erpnext_proposals.utils.quotation import assert_economic_snapshot_complete

	for p in items_plan + req_plan:
		for ch in p["changes"]:
			p["row"].set(ch["field"], ch["new"])

	try:
		assert_economic_snapshot_complete(doc)
		report["guard_after"] = "ok"
	except frappe.ValidationError as e:
		report["guard_after"] = "incompleto"
		report["note"] = (
			"ABORTADO: tras la reparación el snapshot seguiría incompleto (no se persiste nada). "
			f"Detalle: {frappe.utils.strip_html(str(e))[:300]}"
		)
		return report

	if dry_run:
		report["note"] = "DRY-RUN: cambios NO persistidos. El guard pasaría tras aplicar."
		return report

	# ── Persistir atómicamente (ORM, por fila, submitted-safe) + trazabilidad ──
	try:
		for p in items_plan + req_plan:
			for ch in p["changes"]:
				p["row"].db_set(ch["field"], ch["new"], update_modified=False)
		reparados = [f"Item {p['ident']}" for p in items_plan] + [f"Required {p['ident']}" for p in req_plan]
		frappe.get_doc("Quotation", doc.name).add_comment(
			"Comment",
			text=(
				"<b>Legacy economic snapshot compatibility repair</b><br>"
				f"Fecha: {now_datetime()}<br>"
				f"Semántica aplicada: costo externo {LEGACY_SOURCE} (rate 0, locked) + economic_behavior "
				"one_time (sin recurrencia).<br>"
				f"Líneas reparadas: {', '.join(reparados)}"
			),
		)
		frappe.db.commit()  # nosemgrep — reparación administrativa explícita y auditada de snapshot legacy
	except Exception:
		frappe.db.rollback()
		raise

	report["applied"] = True
	report["note"] = (
		"Reparación aplicada y persistida; guard económico completo. Comment de trazabilidad añadido."
	)
	return report
