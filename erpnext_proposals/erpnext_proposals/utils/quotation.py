import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime


def on_quotation_before_insert(doc, method=None):
	"""
	Last line of defense for Quotation creation.
	proposal_group is a required Data field — user enters their CRM deal ID.
	"""
	from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import (
		_next_version,
		_validate_previous_proposal_basic,
		_validate_previous_proposal_under_lock,
		_validate_proposal_version_sequential,
		assert_single_live_proposal_for_group,
	)

	# Issue #17: si la Quotation se creó desde Frappe CRM (campo `crm_deal`) y no se capturó un
	# `proposal_group` manual, se usa el Deal como grupo — copia exacta, sin prefijos ni
	# transformaciones. `doc.get(...)` es seguro en sitios sin el campo `crm_deal` (CRM no instalado).
	if not doc.get("proposal_group") and doc.get("crm_deal"):
		doc.proposal_group = doc.get("crm_deal")

	has_previous = bool(getattr(doc, "previous_proposal", None))
	has_group = bool(getattr(doc, "proposal_group", None))

	if has_previous:
		# ── Path 2: Versioning — controlled flow only ───────────────────
		if not doc.flags.get("from_proposal_versioning"):
			frappe.throw(
				_(
					"Las versiones de propuesta deben crearse usando la acción "
					"'Crear nueva versión de propuesta'. "
					"No se permite crear versiones directamente."
				)
			)
		_validate_previous_proposal_basic(doc)
		_validate_previous_proposal_under_lock(doc)
		assert_single_live_proposal_for_group(doc.proposal_group)
		_validate_proposal_version_sequential(doc)

	elif has_group:
		# ── Path 3: New quotation with explicit proposal_group ──────────
		assert_single_live_proposal_for_group(doc.proposal_group)
		if not getattr(doc, "proposal_version", None):
			doc.set("proposal_version", int(_next_version(doc.proposal_group) or 1))

	else:
		frappe.throw(
			_(
				"El campo 'Grupo de propuesta' es obligatorio. "
				"Ingresa el ID del deal de tu CRM (HubSpot, Salesforce, etc.)."
			)
		)


def on_quotation_validate(doc, method=None):
	# Assign proposal_version = 1 when not set and not a new version created by create_new_proposal_version.
	# Uses validate (not before_insert) because validate is confirmed to run in web context.
	if not doc.get("proposal_version") and not doc.get("previous_proposal"):
		doc.proposal_version = 1
	# Fase 2A: precargar el plazo contractual desde el default de la Company SOLO en la creación y si está
	# vacío. Nunca se reescribe después: si la preventa lo cambia (o lo deja vacío), se respeta.
	_default_contract_term(doc)
	# Banderas de alcance: una fila no puede ser vendible E interna a la vez.
	_validate_internal_cost_flags(doc)
	# Print Format comercial: al aplicar/cambiar la plantilla (o si el override está vacío), poblar
	# `proposal_print_format` con el formato de la Proposal Template. Luego validar (Caso F).
	from erpnext_proposals.erpnext_proposals.utils.print_format import (
		assert_assignable_print_format,
		sync_letter_head_from_template,
		sync_proposal_print_format_from_template,
	)

	sync_proposal_print_format_from_template(doc)
	# Letter Head dedicado: la plantilla puede fijar `letter_head`; se copia al campo NATIVO de la
	# Quotation para que la selección sea EXPLÍCITA por nombre e independiente del default del sitio.
	sync_letter_head_from_template(doc)
	# Change-aware: solo bloquea ADOPTAR un formato no elegible; una propuesta que ya referencia un
	# formato luego deshabilitado (sin cambiarlo) NO se invalida retroactivamente.
	assert_assignable_print_format(doc, "proposal_print_format")
	# Skip scope generation when creating a new version (scope already copied)
	if doc.flags.get("skip_scope_generation"):
		return
	# Structural guard: if this is a new version with scope already copied, skip regeneration
	if doc.get("previous_proposal") and doc.quotation_scope_items:
		return
	# Protect proposal_group: immutable once proposal_version is assigned
	if not doc.is_new() and doc.has_value_changed("proposal_group"):
		if int(doc.proposal_version or 0) >= 1:
			frappe.throw(
				_("El Grupo de propuesta no puede modificarse una vez que la versión ha sido asignada.")
			)
	if not doc.proposal_template:
		return
	# Copia el contenido general del Item a las líneas nativas Quotation Item (congelado): el PDF y las
	# versiones usan la copia, no el Item maestro. Solo en Borrador y generación (no en versiones).
	_copy_item_proposal_fields(doc)
	# Snapshot de Sections narrativas: se construye desde el Template solo si aún está vacío (generación
	# inicial en Borrador); un guardado normal no lo regenera ni consulta maestros.
	_sync_sections_snapshot(doc)
	# Fase 1 bis: precargar Items requeridos configurados por los Items vendidos nuevos, ANTES de generar
	# el alcance, para que sus Scope Items entren en la misma pasada.
	_autoload_required_items(doc)
	_generate_scope_items(doc)


def _validate_internal_cost_flags(doc) -> None:
	"""Combinación inválida: include_in_proposal=1 e is_internal_cost_task=1.

	Una fila del alcance es vendible (visible al cliente) O trabajo interno de costo, nunca ambas.
	"""
	for row in doc.quotation_scope_items or []:
		if row.get("include_in_proposal") and row.get("is_internal_cost_task"):
			frappe.throw(
				_(
					"Fila de alcance '{0}': no puede estar marcada como 'Include in Proposal' y "
					"'Tarea interna de costo' a la vez. Una actividad es vendible o interna, no ambas."
				).format(row.title or row.code or row.scope_item)
			)


def on_quotation_before_update_after_submit(doc, method=None):
	"""Block Update Items on submitted proposals — changes must go through a new version.

	Workflow state transitions also trigger this hook, so we only block
	when workflow_state has NOT changed (i.e. not a workflow action).
	"""
	if not doc.proposal_group:
		return
	if doc.has_value_changed("workflow_state"):
		return
	frappe.throw(
		_(
			"No se permite modificar una propuesta enviada a revisión. "
			"Para realizar cambios, crea una nueva versión desde la propuesta rechazada."
		)
	)


def on_quotation_before_submit(doc, method=None):
	"""Fallback freeze at submit time for documents without a prior snapshot."""
	freeze_proposal(doc)


def _dependency_codes_map(scope_item_names: list) -> dict:
	"""Devuelve {scope_item_name: json_de_codigos_predecesores} para congelar en la Quotation.

	Los predecesores son otros Scope Items (el Link `depends_on` == su código estable, porque
	Scope Item se nombra por `code`). El JSON es una lista ordenada de códigos; ausencia de
	dependencias → ``"[]"``. Una consulta única sobre la child table del catálogo.
	"""
	names = list({n for n in (scope_item_names or []) if n})
	result = {n: [] for n in names}
	if not names:
		return {}
	rows = frappe.get_all(
		"Scope Item Dependency",
		filters={
			"parenttype": "Scope Item",
			"parentfield": "depends_on_scope_items",
			"parent": ["in", names],
		},
		fields=["parent", "depends_on"],
	)
	for r in rows:
		if r.depends_on:
			result[r.parent].append(r.depends_on)
	return {n: json.dumps(sorted(codes), ensure_ascii=False) for n, codes in result.items()}


_SCOPE_GEN_FIELDS = (
	"name",
	"sequence",
	"code",
	"title",
	"description",
	"deliverable",
	"phase",
	"default_activity_type",
	"default_designation",
	"estimated_hours",
	"visible_in_proposal",
	"is_internal_cost_task",
	"planned_start_offset_days",
	"moment",
	"planned_duration_days",
	"is_milestone",
)


def _proposal_settings(company: str | None):
	"""Proposal Settings **de la Company** dada (ADR-0017, Fase 1 bis). Separación estricta por Company:
	sin fallback global. Devuelve el doc cacheado por request o ``None`` si esa Company no tiene settings."""
	if not company:
		return None
	name = frappe.db.get_value("Proposal Settings", {"company": company}, "name")
	if not name:
		return None
	return frappe.get_cached_doc("Proposal Settings", name)


def _configured_required_items(item_code: str, company: str | None) -> list:
	"""Items requeridos configurados para un Item vendido, por el Proposal Settings de la Company
	(ADR-0017, Fase 1 bis). Precedencia: reglas específicas de Item; si no hay, reglas de su Item Group; si
	ninguna, vacío. No se mezclan ambos niveles. Solo PRECARGA (la propuesta manda después)."""
	settings = _proposal_settings(company)
	if not settings:
		return []
	rules = settings.get("required_item_rules") or []
	item_rules = [
		r.required_item
		for r in rules
		if r.source_type == "Item" and r.source == item_code and r.required_item
	]
	if item_rules:
		return list(dict.fromkeys(item_rules))
	group = frappe.db.get_value("Item", item_code, "item_group")
	if not group:
		return []
	group_rules = [
		r.required_item
		for r in rules
		if r.source_type == "Item Group" and r.source == group and r.required_item
	]
	return list(dict.fromkeys(group_rules))


ONE_TIME = "one_time"
_ECONOMIC_BEHAVIORS = ("one_time", "recurring", "infrastructure")


def _default_contract_term(doc) -> None:
	"""Precarga `proposal_contract_term_months` desde el default de la Company (ADR-0018), solo al crear y si
	está vacío. No reescribe un valor ya presente ni un cambio posterior de la preventa. Company sin default
	(0/None) → se deja vacío (comportamiento seguro: sin proyección recurrente por defecto)."""
	if not doc.is_new() or doc.get("proposal_contract_term_months"):
		return
	settings = _proposal_settings(doc.get("company"))
	if not settings:
		return
	default_term = settings.get("default_contract_term_months")
	if default_term:
		doc.proposal_contract_term_months = int(default_term)


def _economic_behavior_for_item(item_code: str, company: str | None) -> tuple:
	"""Comportamiento económico efectivo de un Item, por el Proposal Settings de la Company (ADR-0018).

	Devuelve ``(behavior, interval, interval_count)``. Precedencia idéntica a las demás reglas: regla
	específica de **Item**; si no hay, regla de su **Item Group**; si ninguna, ``one_time`` (default
	implícito). Resolución **estricta por Company**, sin fallback global. Solo clasifica: el importe siempre
	sale de la propuesta (precio de la línea / costo externo), aquí NO hay precio."""
	default = (ONE_TIME, None, None)
	settings = _proposal_settings(company)
	if not settings:
		return default
	rules = settings.get("economic_behavior_rules") or []
	for r in rules:
		if r.source_type == "Item" and r.source == item_code:
			return (r.economic_behavior or ONE_TIME, r.interval, r.interval_count)
	group = frappe.db.get_value("Item", item_code, "item_group")
	if group:
		for r in rules:
			if r.source_type == "Item Group" and r.source == group:
				return (r.economic_behavior or ONE_TIME, r.interval, r.interval_count)
	return default


def _procurement_scope_for_item(item_code: str, company: str | None):
	"""Scope Item de abastecimiento aplicable a un Item COMPRABLE (default de la Company + opt-out por Item).
	Devuelve el code del Scope Item o ``None``. Genérico: no depende de nombres de cliente."""
	settings = _proposal_settings(company)
	if not settings:
		return None
	proc = settings.get("default_procurement_scope_item")
	if not proc:
		return None
	item = frappe.db.get_value(
		"Item", item_code, ["is_purchase_item", "proposal_skip_procurement"], as_dict=True
	)
	if not item or not item.is_purchase_item or item.get("proposal_skip_procurement"):
		return None
	if not frappe.db.get_value("Scope Item", proc, "enabled"):
		return None
	return proc


def _applicable_scope_items(item_code: str, company: str | None) -> list:
	"""Scope Items que aplican a un item_code **en el contexto de una Company**: los de la relación N:M
	(fuente única) MÁS, si el Item es comprable y la Company tiene abastecimiento configurado, el Scope Item
	de abastecimiento. Compartido por la generación y el resync para que ambos vean el MISMO conjunto (el
	resync no elimina el de compra)."""
	from erpnext_proposals.erpnext_proposals.utils.scope_item_links import resolve_scope_items_for_item

	codes = resolve_scope_items_for_item(item_code, enabled_only=True)
	proc = _procurement_scope_for_item(item_code, company)
	if proc and proc not in codes:
		codes = [*list(codes), proc]
	return codes


def _autoload_required_items(doc) -> None:
	"""Precarga Items requeridos configurados al agregar Items VENDIDOS nuevos (ADR-0017, Fase 1 bis).

	Copia el patrón de la generación de alcance: solo para líneas vendidas **nuevas** (diff con
	``get_doc_before_save``); agrega los Required Items configurados que falten (por Item), marcándolos
	``auto_generated=1``. NO repone los que el usuario borró (un guardado normal no trae items nuevos), y
	NO agrega un Item que ya sea línea vendida (evita duplicar una reventa en required_items)."""
	company = doc.get("company")
	before = doc.get_doc_before_save()
	prev_sold = {i.item_code for i in (before.items if before else []) if i.item_code}
	sold_now = {i.item_code for i in (doc.get("items") or []) if i.item_code}
	present_required = {r.item for r in (doc.get("required_items") or []) if r.item}
	for it in doc.get("items") or []:
		if not it.item_code or it.item_code in prev_sold:
			continue  # no es una línea vendida nueva → no precargar
		for req in _configured_required_items(it.item_code, company):
			if req in present_required or req in sold_now:
				continue  # ya está como requerido, o ya es una línea vendida → no duplicar
			doc.append("required_items", {"item": req, "qty": 1, "auto_generated": 1})
			present_required.add(req)


def _append_scope_rows_for_item(doc, item_code: str, existing: set) -> int:
	"""Agrega a ``quotation_scope_items`` las filas FALTANTES de un ``item_code``, resolviendo
	Item → Scope Items por la FUENTE ÚNICA (``resolve_scope_items_for_item``: child N:N + legacy,
	habilitados). ``existing`` = pares (item_code, scope_item) ya presentes; se actualiza in situ.
	No elimina ni actualiza filas existentes y no duplica. Devuelve cuántas filas se agregaron. Incluye el
	Scope Item de abastecimiento si aplica (ver ``_applicable_scope_items``)."""
	names = _applicable_scope_items(item_code, doc.get("company"))
	if not names:
		return 0
	scope_items = frappe.get_all(
		"Scope Item",
		filters={"name": ["in", names]},
		fields=list(_SCOPE_GEN_FIELDS),
		order_by="sequence asc",
	)
	dep_codes = _dependency_codes_map([si.name for si in scope_items])
	added = 0
	for si in scope_items:
		if (item_code, si.name) in existing:
			continue
		doc.append(
			"quotation_scope_items",
			{
				"scope_item": si.name,
				"item_code": item_code,
				"sequence": si.sequence,
				"code": si.code,
				"title": si.title,
				"description": si.description,
				"deliverable": si.deliverable,
				"phase": si.phase,
				"activity_type": si.default_activity_type,
				"designation": si.default_designation,
				"estimated_hours": si.estimated_hours,
				# Valor inicial de include_in_proposal desde el catálogo (visible_in_proposal). Después es
				# propiedad de la propuesta; el resync NO lo sobrescribe.
				"include_in_proposal": 1 if si.visible_in_proposal else 0,
				"is_internal_cost_task": si.is_internal_cost_task or 0,
				# Planeación PMO congelada (opcional; puede venir vacía).
				"planned_start_offset_days": si.planned_start_offset_days,
				# Momento relativo de ejecución (snapshot comercial; puede venir vacío).
				"moment": si.moment,
				"planned_duration_days": si.planned_duration_days,
				"is_milestone": si.is_milestone or 0,
				"dependency_scope_item_codes": dep_codes.get(si.name, "[]"),
				"auto_generated": 1,
			},
		)
		existing.add((item_code, si.name))
		added += 1
	return added


def _source_item_codes(doc) -> list:
	"""item_codes de las líneas que aportan alcance a la propuesta: Items **vendidos** (`doc.items`) +
	**Required Items** (`doc.required_items`, Item nativo no vendido), en ese orden, deduplicados. Ambas
	fuentes usan el MISMO resolver N:M (ADR-0017). El Required Item referencia el Item en el campo `item`."""
	codes = []
	seen = set()
	for it in doc.get("items") or []:
		if it.item_code and it.item_code not in seen:
			codes.append(it.item_code)
			seen.add(it.item_code)
	for ri in doc.get("required_items") or []:
		if ri.item and ri.item not in seen:
			codes.append(ri.item)
			seen.add(ri.item)
	return codes


def _generate_scope_items(doc):
	"""Autopoblado SOLO para líneas NUEVAS (un ``item_code`` de Item vendido o Required Item que no existía
	en el guardado previo). Un guardado normal NO repuebla: si el usuario borró una fila de alcance, no
	reaparece; editar precio/cantidad/texto no reconstruye nada. La captura inicial (documento nuevo)
	genera para todos los Items; agregar un Item vendido o requerido nuevo genera solo su alcance. Recuperar
	faltantes a posteriori es una acción MANUAL explícita (``add_missing_scope_items_from_items``)."""
	before = doc.get_doc_before_save()
	prev_item_codes = set(_source_item_codes(before)) if before else set()
	existing = {
		(row.item_code, row.scope_item)
		for row in (doc.quotation_scope_items or [])
		if row.item_code and row.scope_item
	}
	for item_code in _source_item_codes(doc):
		# item_code que ya estaba en el guardado previo → no repoblar.
		if item_code in prev_item_codes:
			continue
		_append_scope_rows_for_item(doc, item_code, existing)


# Contenido general del Item que se CONGELA en la línea nativa Quotation Item (bloque del servicio).
_FROZEN_ITEM_FIELDS = (
	# item_name incluido: el nombre comercial mostrado en la propuesta se congela desde el Item y el
	# resync explícito lo refresca (p. ej. cuando el catálogo renombra el Item).
	"item_name",
	"description",
	"proposal_methodology",
	"proposal_expected_result",
	"proposal_scope_limit",
)


def _copy_item_proposal_fields(doc, force: bool = False) -> None:
	"""Congela el contenido general del Item (description + proposal_*) en cada línea nativa Quotation
	Item, para que el PDF y las versiones usen la copia y NUNCA relean el Item maestro.

	- Sin `force` (generación inicial): solo congela las líneas NUEVAS (Item recién incorporado). Un
	  guardado normal de un Borrador NO relee ni actualiza líneas ya congeladas (no toca el Item).
	- `force=True` (resync explícito del catálogo en Borrador): refresca los cuatro valores en TODAS
	  las líneas desde el Item maestro.
	"""
	for row in doc.items or []:
		if not row.item_code:
			continue
		if not force and not row.is_new():
			# Guardado normal: la línea ya está congelada; no se relee el Item.
			continue
		vals = frappe.db.get_value("Item", row.item_code, _FROZEN_ITEM_FIELDS, as_dict=True) or {}
		for f in _FROZEN_ITEM_FIELDS:
			row.set(f, vals.get(f))


# Campos del Quotation Scope Item controlados por el catálogo Scope Item.
# Solo estos se refrescan en resync_scope_from_catalog; el resto (include_in_proposal,
# auto_generated, costing_rate, rate_locked, etc.) se preservan.
# include_in_proposal NO está aquí: es propiedad de la propuesta (valor inicial desde
# visible_in_proposal, luego el usuario lo ajusta y el resync lo preserva).
_CATALOG_CONTROLLED_FIELDS = (
	"sequence",
	"code",
	"title",
	"description",
	"deliverable",
	"phase",
	"activity_type",
	"designation",
	"estimated_hours",
	"is_internal_cost_task",
	# Planeación PMO congelada — el resync explícito en Borrador la refresca desde el catálogo.
	"planned_start_offset_days",
	"moment",
	"planned_duration_days",
	"is_milestone",
	"dependency_scope_item_codes",
)


def _catalog_rows_for_items(item_codes: list, company: str | None) -> dict:
	"""Scope Items de catálogo habilitados asociados a los item_codes, por la FUENTE ÚNICA
	(``resolve_scope_items_for_item``: child N:N + legacy), mapeados a los campos del child con clave
	(item_code, scope_item_name). Un mismo Scope Item puede aplicar a varios Items. Incluye el Scope Item
	de abastecimiento de la Company (``_applicable_scope_items``) para que el resync NO lo elimine."""
	result: dict = {}
	codes = list({c for c in (item_codes or []) if c})
	if not codes:
		return result
	per_item = {code: _applicable_scope_items(code, company) for code in codes}
	all_names = sorted({n for names in per_item.values() for n in names})
	if not all_names:
		return result
	rows = frappe.get_all(
		"Scope Item",
		filters={"name": ["in", all_names]},
		fields=[
			"name",
			"sequence",
			"code",
			"title",
			"description",
			"deliverable",
			"phase",
			"default_activity_type",
			"default_designation",
			"estimated_hours",
			"is_internal_cost_task",
			"visible_in_proposal",
			"planned_start_offset_days",
			"moment",
			"planned_duration_days",
			"is_milestone",
		],
		order_by="sequence asc",
	)
	by_name = {si.name: si for si in rows}
	dep_codes = _dependency_codes_map(all_names)
	for code, names in per_item.items():
		for name in names:
			si = by_name.get(name)
			if not si:
				continue
			result[(code, name)] = {
				"sequence": si.sequence,
				"code": si.code,
				"title": si.title,
				"description": si.description,
				"deliverable": si.deliverable,
				"phase": si.phase,
				"activity_type": si.default_activity_type,
				"designation": si.default_designation,
				"estimated_hours": si.estimated_hours,
				"is_internal_cost_task": si.is_internal_cost_task or 0,
				# Planeación PMO congelada — controlada por catálogo (refrescada en resync).
				"planned_start_offset_days": si.planned_start_offset_days,
				# Momento relativo de ejecución — snapshot comercial (refrescado en resync).
				"moment": si.moment,
				"planned_duration_days": si.planned_duration_days,
				"is_milestone": si.is_milestone or 0,
				"dependency_scope_item_codes": dep_codes.get(si.name, "[]"),
				# Solo informativo (valor inicial de include_in_proposal). NO está en
				# _CATALOG_CONTROLLED_FIELDS, por lo que el UPDATE del resync nunca lo sobrescribe.
				"include_in_proposal": 1 if si.visible_in_proposal else 0,
			}
	return result


@frappe.whitelist()
def resync_scope_from_catalog(quotation_name: str) -> dict:
	"""Sincroniza explícitamente la tabla de alcance con el catálogo Scope Item.

	Solo disponible en Borrador. Sobre filas ``auto_generated=1``: actualiza los campos
	controlados por catálogo y elimina las que ya no tienen respaldo (Scope Item deshabilitado/borrado
	o Item quitado de la cotización). **NO agrega** combinaciones faltantes (eso es la acción manual
	``add_missing_scope_items_from_items``). Las filas ``auto_generated=0`` (personalizaciones de la
	propuesta) nunca se tocan.
	"""
	doc = frappe.get_doc("Quotation", quotation_name)
	doc.check_permission("write")

	if doc.docstatus != 0 or doc.get("workflow_state") != "Borrador" or not doc.get("proposal_template"):
		frappe.throw(
			_(
				"La sincronización de alcance solo está disponible en una propuesta en "
				"Borrador con un template asignado."
			)
		)

	item_codes = _source_item_codes(doc)
	catalog = _catalog_rows_for_items(item_codes, doc.get("company"))

	updated = 0
	removed = 0
	kept = []
	for row in list(doc.quotation_scope_items or []):
		if not row.auto_generated:
			# Fila propiedad de la propuesta — nunca se toca ni elimina.
			kept.append(row)
			continue
		fields = catalog.get((row.item_code, row.scope_item))
		if fields is None:
			# Sin respaldo en catálogo (deshabilitado/borrado o Item quitado) → eliminar.
			removed += 1
			continue
		row_changed = False
		for field in _CATALOG_CONTROLLED_FIELDS:
			if row.get(field) != fields[field]:
				row.set(field, fields[field])
				row_changed = True
		if row_changed:
			updated += 1
		kept.append(row)

	doc.set("quotation_scope_items", kept)

	# El resync NO agrega combinaciones faltantes: solo actualiza las filas auto-generadas contra el
	# catálogo y elimina las que perdieron respaldo. Recuperar faltantes es una acción MANUAL explícita
	# (`add_missing_scope_items_from_items`); el guardado y el resync nunca repueblan.

	# Resync explícito: refresca los cuatro valores del bloque del servicio en TODAS las líneas y
	# regenera el snapshot de Sections desde los maestros actuales (actualiza captured_on).
	_copy_item_proposal_fields(doc, force=True)
	_sync_sections_snapshot(doc, force=True)
	doc.save()
	return {
		"updated": updated,
		"removed": removed,
		"total": len(doc.quotation_scope_items),
	}


@frappe.whitelist()
def add_missing_scope_items_from_items(quotation_name: str) -> dict:
	"""Acción MANUAL explícita: revisa TODOS los Items actuales de la Quotation y agrega únicamente las
	combinaciones (Item, Scope Item) FALTANTES, resolviendo por la FUENTE ÚNICA (child N:N + legacy,
	habilitados). No elimina nada, no actualiza filas existentes y no duplica. Es distinta del guardado
	(que nunca repuebla) y del resync (que nunca agrega). Solo en Borrador."""
	doc = frappe.get_doc("Quotation", quotation_name)
	doc.check_permission("write")
	if doc.docstatus != 0 or doc.get("workflow_state") != "Borrador":
		frappe.throw(_("Solo disponible en una propuesta en Borrador."))

	existing = {
		(r.item_code, r.scope_item) for r in (doc.quotation_scope_items or []) if r.item_code and r.scope_item
	}
	added = 0
	for item_code in _source_item_codes(doc):
		added += _append_scope_rows_for_item(doc, item_code, existing)
	if added:
		doc.save()
	return {"added": added, "total": len(doc.quotation_scope_items)}


def freeze_proposal(doc) -> None:
	"""Congela las Sections narrativas (snapshot) y las tarifas de costeo en el punto de revisión formal.

	Se llama en Borrador → En Revisión (y como fallback en Submit). El snapshot ya suele existir desde la
	generación en Borrador: aquí se CONSERVA literalmente; solo se crea como fallback si llega un Draft
	legacy sin snapshot. Las tarifas se congelan siempre (idempotente por fila: rate_locked). Hard-fails
	si el snapshot no puede crearse.
	"""
	if not getattr(doc, "proposal_template", None):
		return  # no template — nothing to freeze

	# Congelar el Print Format comercial efectivo (idempotente).
	from erpnext_proposals.erpnext_proposals.utils.print_format import freeze_effective_print_format

	freeze_effective_print_format(doc)

	# Snapshot: conservar el existente; crear solo si viene un Draft legacy sin snapshot.
	_sync_sections_snapshot(doc)
	_freeze_costing_rates(doc)
	_freeze_item_costs(doc)
	_freeze_economic_behavior(doc)


def _sync_sections_snapshot(doc, force: bool = False) -> None:
	"""Construye/actualiza `proposal_sections_snapshot` desde los maestros (Template + Proposal Section).

	- Sin ``force``: solo si el snapshot está vacío (generación inicial en Borrador o fallback legacy en
	  freeze). Un snapshot ya poblado se conserva LITERALMENTE — un guardado normal no consulta maestros
	  ni regenera contenido aunque las Sections maestras hayan cambiado, y no altera ``captured_on``.
	- ``force=True`` (resync explícito en Borrador): regenera y reemplaza el snapshot desde los maestros
	  actuales, actualizando ``captured_on``.
	"""
	if not getattr(doc, "proposal_template", None):
		return
	if not force and (getattr(doc, "proposal_sections_snapshot", None) or "").strip():
		return  # ya poblado y sin force → conservar literalmente
	doc.proposal_sections_snapshot = json.dumps(_build_sections_snapshot(doc), ensure_ascii=False)


def _build_sections_snapshot(doc) -> list:
	"""Serializa las Sections del Template al snapshot (Jinja crudo, no HTML renderizado).

	Ordena por ``sequence``, excluye Sections deshabilitadas y contenido vacío. Estructura por entrada:
	sequence, title, content, source_section, is_executive_summary, hide_title, captured_on. Hard-fails
	si no puede leer una Section — sin fallback silencioso a maestros vivos en estados formales.
	"""
	try:
		tmpl = frappe.get_doc("Proposal Template", doc.proposal_template)
		snapshot = []
		now = now_datetime().isoformat()

		# Secciones opcionales activadas explícitamente en esta Quotation (Table MultiSelect).
		# Solo aplican a filas del Template marcadas como opcionales (include_by_default=0).
		selected_optional = {
			r.proposal_section for r in (doc.get("proposal_optional_sections") or []) if r.proposal_section
		}

		for row in sorted(tmpl.sections, key=lambda r: r.sequence or 0):
			try:
				ps = frappe.get_doc("Proposal Section", row.proposal_section)
			except Exception as e:
				frappe.throw(
					_("No se pudo leer la sección '{0}': {1}").format(row.proposal_section, str(e)),
					title=_("Error al congelar propuesta"),
				)

			if not ps.enabled:
				continue

			# Sección opcional (include_by_default apagado): solo entra si la propuesta la activó.
			# Las filas con include_by_default=1 (default histórico) conservan el comportamiento previo.
			if not row.include_by_default and row.proposal_section not in selected_optional:
				continue

			content = row.custom_content if row.use_custom_content else ps.content
			if not content:
				continue

			snapshot.append(
				{
					"sequence": row.sequence or 0,
					"title": row.custom_title or ps.title or ps.section_name,
					"content": content,
					"source_section": ps.section_name,
					"is_executive_summary": ps.is_executive_summary or 0,
					# Presentación por Template (Proposal Template Section): congela si el heading se oculta.
					"hide_title": int(row.hide_title or 0),
					# Paginación por Template: congela si la sección inicia página nueva.
					"page_break_before": int(row.page_break_before or 0),
					"captured_on": now,
				}
			)
		return snapshot

	except frappe.exceptions.ValidationError:
		raise  # re-raise frappe.throw calls
	except Exception as e:
		frappe.throw(
			_("No se pudo congelar el contenido de la propuesta: {0}").format(str(e)),
			title=_("Error al congelar propuesta"),
		)


@frappe.whitelist()
def get_template_optional_sections(template: str) -> list:
	"""Secciones OPCIONALES de un Proposal Template para el selector `proposal_optional_sections`.

	Fuente única de verdad: el Template. Devuelve solo las filas con ``include_by_default = 0`` cuya
	Proposal Section esté habilitada. Las filas ``include_by_default = 1`` entran automáticamente y no
	se listan aquí. Ordenadas por ``sequence``. Cada entrada: ``{name, title}``.
	"""
	if not template:
		return []
	rows = frappe.get_all(
		"Proposal Template Section",
		filters={
			"parent": template,
			"parenttype": "Proposal Template",
			"include_by_default": 0,
		},
		fields=["proposal_section"],
		order_by="sequence asc",
	)
	out = []
	for r in rows:
		if not r.proposal_section:
			continue
		ps = frappe.db.get_value(
			"Proposal Section",
			r.proposal_section,
			["name", "title", "section_name", "enabled"],
			as_dict=True,
		)
		if ps and ps.enabled:
			out.append({"name": ps.name, "title": ps.title or ps.section_name})
	return out


def _freeze_costing_rates(doc) -> None:
	"""Freeze costing rates from Proposal Cost Matrix into each Scope Item."""
	from erpnext_proposals.erpnext_proposals.utils.cost_matrix import get_designation_cost

	now = now_datetime()
	for row in doc.quotation_scope_items or []:
		# Costeo/congelamiento: filas vendibles O internas de costo.
		if not (row.include_in_proposal or row.is_internal_cost_task):
			continue
		if row.rate_locked:
			continue  # already locked — never overwrite
		rate, source = get_designation_cost(row.designation, row.activity_type)
		row.costing_rate = flt(rate)
		row.rate_source = source
		row.rate_locked = 1
		row.rate_locked_on = now


def _freeze_item_costs(doc) -> None:
	"""Congela el COSTO EXTERNO por línea (Item vendido + Required Item) en Borrador → En Revisión.

	Aditivo al costo laboral (que se congela en ``_freeze_costing_rates``). Idempotente por fila
	(``cost_locked``). Resuelve en vivo con el pricing NATIVO (``resolve_external_cost``: gate
	``is_purchase_item`` → Item Price de compra → last_purchase → valuation). Sin costo → rate 0,
	source ``sin_costo``, locked=1: la propuesta histórica NO vuelve a consultar pricing vivo (ADR-0017)."""
	from erpnext_proposals.erpnext_proposals.utils.item_cost import resolve_external_cost

	txn = doc.get("transaction_date")
	for row in doc.get("items") or []:
		if row.get("proposal_cost_locked"):
			continue  # already locked — never overwrite
		rate, source = resolve_external_cost(row.item_code, row.get("uom"), txn)
		row.proposal_frozen_cost_rate = flt(rate)
		row.proposal_frozen_cost_source = source
		row.proposal_cost_locked = 1
	for row in doc.get("required_items") or []:
		if row.get("cost_locked"):
			continue
		rate, source = resolve_external_cost(row.item, row.get("uom"), txn)
		row.frozen_cost_rate = flt(rate)
		row.frozen_cost_source = source
		row.cost_locked = 1


def _freeze_economic_behavior(doc) -> None:
	"""Congela el COMPORTAMIENTO ECONÓMICO efectivo por línea en Borrador → En Revisión (ADR-0018).

	Snapshot mínimo (behavior/interval/interval_count) resuelto en vivo desde el Proposal Settings de la
	Company al momento del freeze. Idempotente por fila (no sobrescribe si ya hay behavior congelado). Tras
	En Revisión, la Evaluación Económica usa exclusivamente este snapshot: cambios posteriores en la
	configuración NO alteran la propuesta histórica. El plazo efectivo es `proposal_contract_term_months`,
	que ya vive en la Quotation y queda inmutable al someterse."""
	company = doc.get("company")
	for row in doc.get("items") or []:
		if row.get("proposal_economic_behavior"):
			continue
		behavior, interval, count = _economic_behavior_for_item(row.item_code, company)
		row.proposal_economic_behavior = behavior
		row.proposal_billing_interval = interval or ""
		row.proposal_billing_interval_count = int(count or 0)
	for row in doc.get("required_items") or []:
		if row.get("economic_behavior"):
			continue
		behavior, interval, count = _economic_behavior_for_item(row.item, company)
		row.economic_behavior = behavior
		row.billing_interval = interval or ""
		row.billing_interval_count = int(count or 0)


def attach_proposal_pdfs(doc) -> None:
	"""Generate and attach PDF snapshots when proposal enters formal review.

	Genera Propuesta Comercial y Rentabilidad Estimada, ambas como ``File`` PRIVADO
	(``is_private=1``): son la evidencia formal de la propuesta y no deben quedar accesibles por URL
	pública. Los usuarios autorizados las abren/descargan normalmente desde los adjuntos de la
	Quotation (Frappe valida el permiso sobre el documento adjunto).
	PDF generation failure is non-blocking but logged with a visible warning.
	The snapshot JSON is the hard protection; the PDF is the evidence artifact.
	"""
	from erpnext_proposals.erpnext_proposals.utils.print_format import (
		resolve_commercial_print_format,
		resolve_sow_print_format,
	)

	commercial_pf = resolve_commercial_print_format(doc)
	_attach_pdf(
		doc,
		print_format=commercial_pf,
		filename=f"{commercial_pf} - {doc.name}",
		is_private=1,
	)
	_attach_pdf(
		doc,
		print_format="Rentabilidad Estimada",
		filename=f"Rentabilidad Estimada - {doc.name}",
		is_private=1,
	)
	# SOW: OTRA REPRESENTACIÓN del mismo contenido congelado. Mismo pipeline (_attach_pdf → renderer),
	# mismo snapshot, misma protección histórica. Solo se adjunta si la plantilla define un PF de SOW.
	sow_pf = resolve_sow_print_format(doc)
	if sow_pf:
		_attach_pdf(
			doc,
			print_format=sow_pf,
			filename=f"SOW - {doc.name}",
			is_private=1,
		)
	# Signal client to reload attachments once files are committed
	frappe.publish_realtime(
		"erpnext_proposals_pdfs_attached",
		{"doctype": doc.doctype, "name": doc.name},
		user=frappe.session.user,
		after_commit=True,
	)


def _attach_pdf(doc, print_format: str, filename: str, is_private: int) -> None:
	"""Generate a PDF from a Print Format and attach it to the Quotation."""
	try:
		from frappe.utils.file_manager import save_file

		from erpnext_proposals.erpnext_proposals.utils.official_document_protection import (
			INTERNAL_REPLACE_FLAG,
			OFFICIAL_FLAG_FIELD,
		)
		from erpnext_proposals.erpnext_proposals.utils.print_format import render_proposal_pdf

		# Genérico: aplica portada separada (2 renders + merge) si la Proposal Template lo pide y es su
		# Print Format comercial; en otro caso un solo render. No afecta otros Print Formats.
		pdf_bytes = render_proposal_pdf(doc, print_format)

		# Remove previous version(s) of this attachment if they exist. `save_file` añade un sufijo hash
		# al nombre, por lo que la coincidencia es por PREFIJO (`{filename}%`) + `attached_to`, NO por
		# nombre exacto (que nunca casa por el hash → duplicaba en cada regeneración). La coincidencia
		# NO filtra por `is_private`: cada documento (comercial / rentabilidad) tiene un prefijo de
		# nombre distinto, así que basta el prefijo para identificar sus versiones previas, y así un
		# re-freeze reemplaza también cualquier copia heredada guardada con otra privacidad (p. ej. un
		# comercial público de antes de que ambos pasaran a privados). La versión previa puede estar
		# marcada como documento oficial y protegida contra borrado; el reemplazo por el propio flujo de
		# generación se exime de forma explícita mediante INTERNAL_REPLACE_FLAG (única vía además de
		# Administrator). El flag se limpia inmediatamente.
		previous = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": doc.doctype,
				"attached_to_name": doc.name,
				"file_name": ["like", f"{filename}%"],
			},
			pluck="name",
		)
		for _prev in previous:
			frappe.flags[INTERNAL_REPLACE_FLAG] = True
			try:
				frappe.delete_doc("File", _prev, ignore_permissions=True)
			finally:
				frappe.flags[INTERNAL_REPLACE_FLAG] = False

		_official = save_file(
			fname=f"{filename}.pdf",
			content=pdf_bytes,
			dt=doc.doctype,
			dn=doc.name,
			is_private=is_private,
		)
		# Marcar inequívocamente el archivo como documento oficial de la propuesta (protegido).
		frappe.db.set_value("File", _official.name, OFFICIAL_FLAG_FIELD, 1, update_modified=False)

	except Exception as e:
		frappe.log_error(f"Error generating PDF '{print_format}' for {doc.name}: {e}")
		frappe.msgprint(
			_(
				"No se pudo generar el PDF '{0}'. El proceso continúa pero revisa los adjuntos manualmente."
			).format(print_format),
			indicator="orange",
			alert=True,
		)


@frappe.whitelist()
def get_proposal_documents_status(quotation: str) -> dict:
	"""Comprobación REAL de que los documentos oficiales de la propuesta ya fueron generados/adjuntados.

	Los documentos oficiales los produce ``attach_proposal_pdfs`` al congelar (Borrador → En Revisión):
	la propuesta comercial (privada, ``{formato efectivo} - {name}``) y la propuesta económica /
	Rentabilidad Estimada (privada, ``Rentabilidad Estimada - {name}``). ``save_file`` puede añadir un
	sufijo hash al nombre, por lo que la coincidencia es por PREFIJO. La generación es no-bloqueante
	(puede fallar), así que ``docstatus`` no basta: se verifica la existencia real de cada adjunto.

	Lo usa el botón ``Propuesta`` (JS) para ocultar las acciones de RE-GENERAR ("Imprimir …") de cada
	documento oficial una vez que ese documento existe, sin quitar el acceso a los adjuntos ya generados.
	"""
	from erpnext_proposals.erpnext_proposals.utils.print_format import resolve_commercial_print_format

	doc = frappe.get_doc("Quotation", quotation)
	doc.check_permission("read")

	def _attached(prefix: str, is_private: int) -> bool:
		return bool(
			frappe.db.exists(
				"File",
				{
					"attached_to_doctype": "Quotation",
					"attached_to_name": doc.name,
					"is_private": is_private,
					"file_name": ["like", f"{prefix}%"],
				},
			)
		)

	commercial_pf = resolve_commercial_print_format(doc)
	commercial = _attached(f"{commercial_pf} - {doc.name}", 1)
	rentabilidad = _attached(f"Rentabilidad Estimada - {doc.name}", 1)
	return {
		"commercial": commercial,
		"rentabilidad": rentabilidad,
		"official_present": commercial and rentabilidad,
	}
