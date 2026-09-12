"""Contrato económico canónico Project ↔ Quotations (erpnext_proposals).

Responde el **autorizado vigente** de un Project: original (propuesta raíz Ganada) + addendas aplicadas.

    Autorizado = Original + Σ(addendas aplicadas)

para cada magnitud INDEPENDIENTE: revenue, cost, margin, labor, external. `margin_pct` no se suma:
se deriva de `authorized_margin / authorized_revenue`.

Fuente económica ÚNICA por Quotation: ``get_economic_evaluation(quotation).totals`` (revenue, total_cost,
labor, external, margin). Este módulo NO reimplementa ninguna fórmula (horas*tarifa, recurrencia,
financiamiento, etc.). El **financiamiento queda excluido**: el costo autorizado usa exclusivamente
``totals.total_cost`` (que ya excluye el costo financiero).

`Project.estimated_costing` es un **espejo operacional** derivado y sincronizado desde las Quotations
congeladas (idempotente, desde cero, sin flag, sin acumulación incremental). La fuente histórica sigue
siendo cada Quotation congelada; una edición manual de `estimated_costing` se corrige al siguiente sync.

Fail-closed: una Quotation submitted que debería estar congelada pero carece de snapshot económico
completo, o una moneda incompatible con la base, **bloquean** — NO se reconstruye el histórico con datos
vivos ni se mezclan monedas. No depende de `pmo` ni de `PMO Change Request.impact_amount`.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from erpnext_proposals.erpnext_proposals.utils.addendum import is_addendum_group, resolve_root_group
from erpnext_proposals.erpnext_proposals.utils.economic_calendar import _evaluate_doc
from erpnext_proposals.erpnext_proposals.utils.quotation import assert_economic_snapshot_complete

# Magnitudes agregables 1:1 desde totals (margin_pct NO se agrega: se deriva).
_MAGNITUDES = ("revenue", "total_cost", "margin", "labor", "external")


# ── Guards fail-closed ───────────────────────────────────────────────────────
# El invariante "snapshot económico completo" vive en una única función canónica
# (`quotation.assert_economic_snapshot_complete`), compartida con submit y workflow. Aquí solo se consume.


def _assert_same_base_currency(doc, base_currency: str | None) -> None:
	"""Moneda v1: la Quotation debe usar la moneda base de la Company y ``conversion_rate`` compatible con 1.
	Sin FX propio: cualquier violación bloquea la sincronización (no se mezclan monedas)."""
	cur = doc.get("currency")
	if base_currency and cur and cur != base_currency:
		frappe.throw(
			_(
				"Moneda incompatible: la Cotización {0} usa {1} y la base del Project es {2}. La normalización "
				"multidivisa es un cambio posterior; la sincronización se detiene (fail-closed)."
			).format(doc.name, cur, base_currency)
		)
	cr = flt(doc.get("conversion_rate") or 0)
	if cr and abs(cr - 1.0) > 1e-9:
		frappe.throw(
			_("La Cotización {0} tiene conversion_rate {1} (≠ 1); sin FX propio en v1 (fail-closed).").format(
				doc.name, cr
			)
		)


# ── Resolución Project → Quotations (nunca por nombre ni heurística) ─────────


def _resolve_root_quotation(project: str) -> str:
	"""Propuesta raíz de un Project: docstatus=1 + Ganada + no superseded + proposal_project==project +
	grupo NORMAL (no addenda). Debe existir **exactamente una**; 0 o >1 = estado inconsistente → fail-closed."""
	rows = frappe.get_all(
		"Quotation",
		filters={
			"proposal_project": project,
			"docstatus": 1,
			"workflow_state": "Ganada",
			"superseded_by_proposal": ("in", ("", None)),
		},
		fields=["name", "proposal_group"],
	)
	roots = [r.name for r in rows if not is_addendum_group(r.proposal_group)]
	if len(roots) != 1:
		frappe.throw(
			_(
				"Estado inconsistente: se esperaba exactamente 1 propuesta raíz Ganada para el Project {0}; "
				"se encontraron {1} ({2})."
			).format(project, len(roots), ", ".join(sorted(roots)) or "ninguna")
		)
	return roots[0]


def _applied_addenda(project: str, root_group: str) -> list[str]:
	"""Addendas APLICADAS: Ganada + submitted + no superseded + mismo root + proposal_project==project.
	La aplicación se decide por `proposal_project` (que fija `apply_addendum_to_project`), NUNCA por `pmo`."""
	rows = frappe.get_all(
		"Quotation",
		filters={
			"proposal_project": project,
			"docstatus": 1,
			"workflow_state": "Ganada",
			"superseded_by_proposal": ("in", ("", None)),
		},
		fields=["name", "proposal_group"],
	)
	return sorted(
		r.name
		for r in rows
		if is_addendum_group(r.proposal_group) and resolve_root_group(r.proposal_group) == root_group
	)


def _pending_changes(root_group: str, project: str) -> list[str]:
	"""Addendas del root Ganada+submitted+no superseded que **aún no** están aplicadas a este Project
	(proposal_project != project). Son cambios pendientes; NO forman parte del autorizado."""
	rows = frappe.get_all(
		"Quotation",
		filters={
			"proposal_group": ("like", f"{root_group}-ADD-%"),
			"docstatus": 1,
			"workflow_state": "Ganada",
			"superseded_by_proposal": ("in", ("", None)),
		},
		fields=["name", "proposal_group", "proposal_project"],
	)
	return sorted(
		r.name
		for r in rows
		if is_addendum_group(r.proposal_group)
		and resolve_root_group(r.proposal_group) == root_group
		and r.proposal_project != project
	)


# ── Contrato económico ───────────────────────────────────────────────────────


def get_project_authorized_economics(project: str) -> dict:
	"""Autorizado vigente de un Project = original (root) + addendas aplicadas. Solo lectura.

	Fail-closed ante: root no única, snapshot económico incompleto en una Quotation submitted, o moneda
	incompatible con la base. `authorized_margin_pct` derivado (no sumado). Financiamiento excluido."""
	if not frappe.db.exists("Project", project):
		frappe.throw(_("El Project {0} no existe.").format(project))

	root_name = _resolve_root_quotation(project)
	root_doc = frappe.get_doc("Quotation", root_name)
	root_group = resolve_root_group(root_doc.proposal_group)
	base_currency = (
		frappe.db.get_value("Company", root_doc.company, "default_currency") if root_doc.company else None
	)
	applied = _applied_addenda(project, root_group)

	def _totals(name: str) -> dict:
		doc = frappe.get_doc("Quotation", name)
		assert_economic_snapshot_complete(doc)  # fail-closed (guard canónico compartido)
		_assert_same_base_currency(doc, base_currency)  # fail-closed
		# Derivación de SISTEMA (espejo económico): usa el MISMO motor que `get_economic_evaluation` —su
		# núcleo `_evaluate_doc`, idéntico plazo/scope— pero sin el gate `check_permission("read")` del wrapper
		# whitelisted: la autoridad para aplicar/sincronizar es WRITE sobre el Project (ya validada), no la
		# lectura de Quotations del usuario operativo (owner-only en pmo). NO reimplementa ninguna fórmula.
		return _evaluate_doc(doc, term=cint(doc.get("proposal_contract_term_months")), scope_scale=1.0)[
			"totals"
		]

	def _row(name: str, role: str, t: dict) -> dict:
		return {"name": name, "role": role, **{k: flt(t.get(k)) for k in _MAGNITUDES}}

	root_t = _totals(root_name)
	quotations = [_row(root_name, "root", root_t)]
	changes = {k: 0.0 for k in _MAGNITUDES}
	for a in applied:
		at = _totals(a)
		for k in _MAGNITUDES:
			changes[k] += flt(at.get(k))
		quotations.append(_row(a, "applied_change", at))

	def trio(k: str) -> tuple:
		o = flt(root_t.get(k))
		c = changes[k]
		return o, c, o + c

	rev = trio("revenue")
	cost = trio("total_cost")
	mar = trio("margin")
	lab = trio("labor")
	ext = trio("external")

	return {
		"root_quotation": root_name,
		"currency": root_doc.currency,
		"base_currency": base_currency,
		"currency_consistent": True,  # invariante: si no lo fuera, _assert_same_base_currency ya bloqueó
		"original_revenue": rev[0],
		"applied_changes_revenue": rev[1],
		"authorized_revenue": rev[2],
		"original_cost": cost[0],
		"applied_changes_cost": cost[1],
		"authorized_cost": cost[2],
		"original_margin": mar[0],
		"applied_changes_margin": mar[1],
		"authorized_margin": mar[2],
		"authorized_margin_pct": (mar[2] / rev[2] * 100.0) if rev[2] else 0.0,  # DERIVADO, nunca sumado
		"original_labor": lab[0],
		"applied_changes_labor": lab[1],
		"authorized_labor": lab[2],
		"original_external": ext[0],
		"applied_changes_external": ext[1],
		"authorized_external": ext[2],
		"quotations": quotations,
		"pending_changes": _pending_changes(root_group, project),
		"financing_excluded": True,
	}


def sync_project_authorized_cost(project: str) -> dict:
	"""Recomputa el autorizado desde cero y espeja ``Project.estimated_costing = authorized_cost``.

	Idempotente (misma entrada → mismo valor), sin acumulación incremental, sin flag, sin otra fuente.
	Escribe con ``set_value(update_modified=False)`` — NO ``save()`` — para no disparar `update_costing`
	nativo ni tocar `total_costing_amount` (ERPNext sigue siendo su autoridad). Sin commit interno: es
	atómico con la transacción del caller (create/apply). Devuelve el desglose para trazabilidad."""
	econ = get_project_authorized_economics(project)  # fail-closed
	frappe.db.set_value(
		"Project", project, "estimated_costing", econ["authorized_cost"], update_modified=False
	)
	return econ
