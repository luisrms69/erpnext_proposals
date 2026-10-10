import json

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate

from erpnext_proposals.erpnext_proposals.utils.permissions import assert_can_manage_proposals
from erpnext_proposals.erpnext_proposals.utils.phase import phase_sequence


def _parse_dep_codes(raw) -> list:
	"""Parsea el JSON congelado de códigos de Scope Items predecesores. Tolerante a valores vacíos."""
	if not raw:
		return []
	try:
		value = json.loads(raw)
	except ValueError, TypeError:
		return []
	return [str(c) for c in value if c] if isinstance(value, list) else []


def _offset_value(raw):
	"""Convierte el offset (Data nullable) a int, o None si NO hay offset explícito.

	Vacío/NULL → None (sin offset → se programa por dependencias o queda sin fecha).
	'0' → 0 (inicio explícito en la fecha de inicio del proyecto). ±N → int. La conversión a int
	ocurre solo aquí (al calcular), nunca se almacena convertido."""
	if raw is None:
		return None
	s = str(raw).strip()
	if s == "":
		return None
	try:
		return int(s)
	except ValueError:
		return None


# Nombre del Project: `Project.project_name` es Data (varchar 140), único.
_PROJECT_NAME_MAXLEN = 140
_PROJECT_NAME_SEP = " — "


def _build_project_name(customer_name: str, proposal_title, proposal_group) -> str:
	"""Nombre del Project con el **Proposal Group al FINAL** (Tema 2).

	- Base = `proposal_title` si existe; si no, `<customer> — <group>` (regla previa).
	- El Proposal Group se añade al final con el separador consistente de la app, salvo que la base **ya
	  termine** con ese group como sufijo inequívoco (precedido de espacio/guion) → no se duplica ni se recorta
	  ninguna palabra legítima.
	- Sin Proposal Group: se conserva el nombre base tal cual (sin guiones vacíos, `None` ni espacios sobrantes).
	- Respeta el límite del campo (140): si el nombre excede, se trunca **solo la base** de forma determinista,
	  conservando el Proposal Group completo al final.
	"""
	group = (proposal_group or "").strip()
	base = (proposal_title or "").strip()
	if not base:
		base = (
			f"{customer_name}{_PROJECT_NAME_SEP}{group}".strip() if group else (customer_name or "").strip()
		)
	if not group:
		return base[:_PROJECT_NAME_MAXLEN].rstrip() or "Proyecto"
	# ¿el group ya está al final como sufijo inequívoco (con separador delante o siendo el nombre completo)?
	already = base == group or (
		base.endswith(group) and base[-len(group) - 1 : -len(group)] in {" ", "-", "—"}
	)
	if already:
		if len(base) <= _PROJECT_NAME_MAXLEN:
			return base
		# Excede: conservar el group al final; truncar solo la cabecera.
		head_max = _PROJECT_NAME_MAXLEN - len(group) - 1
		head = base[: -len(group)].rstrip(" -—")
		return (f"{head[:head_max]} " if head_max > 0 else "") + group
	suffix = f"{_PROJECT_NAME_SEP}{group}"
	keep = _PROJECT_NAME_MAXLEN - len(suffix)
	if keep <= 0:
		return group[:_PROJECT_NAME_MAXLEN].strip()
	return f"{base[:keep].rstrip()}{suffix}"


def _resolve_project_type(quotation) -> str | None:
	"""Project Type inferido de los **paquetes de alcance** presentes en `required_items` (issue #55, commit 2).

	Cada Item-paquete puede declarar el custom field opcional `proposal_project_type`. Política **fail-closed**:
	0 tipos → ``None`` (Project sin tipo); 1 tipo distinto → ese tipo; **≥2 tipos distintos → bloquear** (nunca
	last-wins), identificando los paquetes y tipos en conflicto. Solo considera `required_items` (los paquetes),
	**nunca** `Quotation.items`: la metodología la define el paquete, no el servicio vendido.

	El guard `has_field` mantiene el comportamiento seguro (sin tipo) si el sitio aún no aplicó el custom field
	(`bench migrate`) — sin errores de columna inexistente."""
	if not frappe.get_meta("Item").has_field("proposal_project_type"):
		return None
	by_type: dict[str, list[str]] = {}
	for r in quotation.get("required_items") or []:
		if not r.item:
			continue
		pt = frappe.db.get_value("Item", r.item, "proposal_project_type")
		if pt:
			by_type.setdefault(pt, []).append(r.item)
	if not by_type:
		return None
	if len(by_type) == 1:
		return next(iter(by_type))
	detalle = "; ".join(f"{t} ← {', '.join(sorted(set(items)))}" for t, items in sorted(by_type.items()))
	frappe.throw(
		_(
			"No se puede crear el Proyecto: hay paquetes de alcance con tipos de proyecto distintos "
			"({0}). Deja un solo tipo de proyecto entre los paquetes antes de crear el Proyecto."
		).format(detalle)
	)


def _validate_scope_for_project(quotation) -> list:
	"""Preflight compartido por la creación y por el addendum: valida Proposal Template + que exista
	programa que generar (≥1 Item vendido o ≥1 fila ejecutable). Se ejecuta ANTES de resolver/crear
	cualquier Project, para no dejar un Project huérfano si un preflight falla. La fase dejó de ser
	obligatoria (ya no agrupa ni genera Tasks padre). Devuelve las filas ejecutables (hijas de scope)."""
	if not quotation.proposal_template:
		frappe.throw(_("La Cotización no tiene Proposal Template asignado."))
	# Filas ejecutables: vendibles O internas de costo (participan en costo y Tasks hijas).
	exec_rows = [
		r for r in quotation.quotation_scope_items if r.include_in_proposal or r.is_internal_cost_task
	]
	# Cada Item vendido genera su Task padre (con Task operativa si no tiene alcance), así que una
	# propuesta con Items vendidos SÍ genera Proyecto aunque sea de solo licenciamiento.
	if not exec_rows and not (quotation.get("items") or []):
		frappe.throw(
			_(
				"No hay Items vendidos ni actividades ejecutables en esta propuesta: no hay programa "
				"que generar para el Proyecto."
			)
		)
	return exec_rows


@frappe.whitelist()
def create_project_from_quotation(quotation_name: str):
	assert_can_manage_proposals()

	from erpnext_proposals.erpnext_proposals.utils.addendum import is_addendum_group
	from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import (
		assert_can_create_project,
	)

	quotation = frappe.get_doc("Quotation", quotation_name)

	# Guard fail-closed: una addenda NUNCA crea Project. Su alcance se incorpora al Project raíz existente
	# mediante `apply_addendum_to_project` (aplicación explícita gobernada por PMO), nunca por esta ruta.
	if is_addendum_group(quotation.proposal_group):
		frappe.throw(
			_(
				"Una addenda no crea un Proyecto. Su alcance se incorpora al Proyecto de la propuesta raíz "
				"mediante la aplicación explícita de la addenda."
			)
		)

	assert_can_create_project(quotation)  # validates docstatus, state, superseded, project

	exec_rows = _validate_scope_for_project(quotation)

	# Project Type inferido de los paquetes (issue #55): se valida ANTES de crear nada — si hay ambigüedad,
	# se bloquea sin dejar Project a medias.
	resolved_project_type = _resolve_project_type(quotation)

	# ── Project (idempotente: reutiliza si ya existe) ──────────────────────────
	if quotation.proposal_project and frappe.db.exists("Project", quotation.proposal_project):
		project = frappe.get_doc("Project", quotation.proposal_project)
	else:
		customer = quotation.party_name
		customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
		project_name = _build_project_name(customer_name, quotation.proposal_title, quotation.proposal_group)
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
					"project_type": resolved_project_type or None,
				}
			)
			project.insert(ignore_permissions=True)
		frappe.db.set_value(
			"Quotation", quotation_name, "proposal_project", project.name, update_modified=False
		)

	res = _materialize_scope_into_project(quotation, project, exec_rows)
	# Contrato económico: espeja Project.estimated_costing con el autorizado (root recién creado) ANTES del
	# commit existente, para que un fallo económico no deje un Project económicamente incompleto.
	from erpnext_proposals.erpnext_proposals.utils.project_economics import sync_project_authorized_cost

	sync_project_authorized_cost(project.name)
	frappe.db.commit()  # nosemgrep
	return res


def auto_create_project_on_won(quotation_name: str) -> None:
	"""Job post-commit (issue #39, Fase 1): crea el Project al ganar la propuesta **reutilizando**
	``create_project_from_quotation`` (idempotente, con sus preflights, Project Type, materialización
	Scope Items → Tasks y su modelo de permisos). No duplica lógica ni crea un segundo camino de generación.

	Guards re-chequeados en el job (el estado pudo cambiar entre encolar y ejecutar): solo actúa si la
	Quotation sigue ``Ganada`` (``docstatus=1``) y no tiene ya un Project. **Fail-soft:** NO revierte la
	transición ya commiteada; si un preflight bloquea (p. ej. fila ejecutable sin fase),
	``create_project_from_quotation`` lanza ANTES de crear nada → no queda Project parcial y el fallo queda
	visible por los mecanismos estándar de Frappe (Error Log / job fallido). El botón manual sigue de respaldo."""
	from erpnext_proposals.erpnext_proposals.utils.addendum import is_addendum_group

	doc = frappe.get_doc("Quotation", quotation_name)
	if doc.docstatus != 1 or doc.get("workflow_state") != "Ganada":
		return
	# Defensa en profundidad: aunque `_ensure_project_on_won` ya excluye addendas al encolar, el job
	# revalida — una addenda nunca crea Project por esta vía.
	if is_addendum_group(doc.proposal_group):
		return
	if doc.get("proposal_project") and frappe.db.exists("Project", doc.proposal_project):
		return
	create_project_from_quotation(quotation_name)


def _origin_display(row) -> tuple:
	"""Nombre legible + qty + UOM de la ocurrencia origen de una fila de scope, por `(source_type,
	source_row)`. Solo lectura; sin campos nuevos. Fallback al item_code si no se resuelve."""
	if row.get("source_type") == "sold" and row.get("source_row"):
		qi = frappe.db.get_value("Quotation Item", row.source_row, ["item_name", "qty", "uom"], as_dict=True)
		if qi:
			return (qi.item_name or row.item_code, qi.qty, qi.uom)
	elif row.get("source_type") == "required" and row.get("source_row"):
		ri = frappe.db.get_value(
			"Proposal Required Item", row.source_row, ["item", "qty", "uom"], as_dict=True
		)
		if ri:
			return (frappe.db.get_value("Item", ri.item, "item_name") or ri.item, ri.qty, ri.uom)
	return (row.item_code, None, None)


def _scope_task_subject(row, purchase_code: str | None) -> str:
	"""Subject humano de la Task hija de scope. Para el Scope fallback de COMPRA usa la identidad de la
	ocurrencia origen (nombre/qty/UOM); para el resto, título — item_code. (El subject "Entregar — <item>"
	de la Task operativa de un Item vendido sin alcance se arma en la materialización, no aquí.)"""
	sc = row.get("scope_item")
	if sc and purchase_code and sc == purchase_code:
		name, qty, uom = _origin_display(row)
		suffix = ""
		if qty:
			suffix = f" × {flt(qty):g}" + (f" {uom}" if uom else "")  # noqa: RUF001
		return _("Comprar") + f" — {name}{suffix}"
	if row.item_code:
		return f"{row.title or row.code} — {row.item_code}"
	return row.title or row.code


def _materialize_scope_into_project(quotation, project, exec_rows) -> dict:
	"""Materializa el programa sobre un Project **ya resuelto**: una Task padre (`is_group=1`) por cada
	**ocurrencia de Item contratada**, con sus Scope Items ejecutables como Tasks hijas; si una ocurrencia
	**vendida** no tiene alcance ejecutable, una única **Task operativa** inicial (sin crear Scope Items
	artificiales). NO crea Project y NO hace `frappe.db.commit()` (composable: el caller decide la
	transacción). Idempotente por `(project, source_quotation_item_row, is_group=1)` para el padre,
	`(project, source_quotation_item_row, is_group=0)` para la Task operativa, y
	`(project, source_quotation_scope_item)` para las hijas de scope: reejecutar —o reaplicar la misma
	addenda— no duplica. La fase ya NO agrupa ni es obligatoria."""
	from erpnext_proposals.erpnext_proposals.utils.quotation import _proposal_settings, _source_rows

	_settings = _proposal_settings(quotation.get("company"))
	_purchase_code = _settings.get("default_purchase_scope_item") if _settings else None
	counters = {
		"parent_created": 0,
		"parent_reused": 0,
		"tasks_created": 0,
		"tasks_skipped": 0,
	}

	# Ocurrencias (filas origen) del documento, con orden y metadatos para el padre-por-Item.
	occ_rows = _source_rows(quotation)
	occ_order = {src["source_row"]: i for i, src in enumerate(occ_rows)}
	occ_meta = {src["source_row"]: src for src in occ_rows}
	item_parent_by_row: dict = {}

	def _item_parent_task(source_row: str) -> str:
		"""Task padre por **ocurrencia de Item** (`is_group=1`). Idempotente por
		`(project, source_quotation_item_row, is_group=1)` — inequívocamente distinta de la Task operativa
		(`is_group=0`) aunque compartan `source_quotation_item_row`. PMO puede editar/ampliar sin romper la
		identidad (el campo es read-only y no se toca)."""
		if source_row in item_parent_by_row:
			return item_parent_by_row[source_row]
		existing = frappe.db.get_value(
			"Task",
			{"project": project.name, "source_quotation_item_row": source_row, "is_group": 1},
			"name",
		)
		if existing:
			counters["parent_reused"] += 1
			name = existing
		else:
			src = occ_meta.get(source_row) or {"item_code": None}
			subject, _q, _u = _origin_display(frappe._dict(src))
			parent = frappe.get_doc(
				{
					"doctype": "Task",
					"subject": subject or src.get("item_code") or source_row,
					"project": project.name,
					"is_group": 1,
					"expected_time": 0,
					"status": "Open",
					"source_quotation": quotation.name,
					"source_quotation_item_row": source_row,
				}
			)
			parent.insert(ignore_permissions=True)
			counters["parent_created"] += 1
			name = parent.name
		item_parent_by_row[source_row] = name
		return name

	# Orden: por ocurrencia (orden del documento), luego fase (sub-orden cuando exista), scope e idx.
	exec_rows.sort(
		key=lambda r: (occ_order.get(r.source_row, 1 << 30), phase_sequence(r.phase), r.sequence or 0, r.idx)
	)

	# Nodos contratados con su Task, para los pasos de dependencias y programación. Incluye Tasks
	# reutilizadas de una corrida previa: un reintento completa deps/fechas faltantes sin duplicar.
	contracted: list = []  # [{scope, source_row, task, parent, offset, duration, milestone, dep_codes}]
	# Resolución de dependencias por OCURRENCIA (Tema 1): (source_row, scope_code) -> Task; y todas las
	# materializaciones de cada scope_code, para el fallback único (sin last-wins ni regla cross-item).
	task_by_row_scope: dict = {}
	task_by_scope_all: dict = {}
	rows_with_children: set = set()  # source_rows que materializaron ≥1 Task hija de scope

	for row in exec_rows:
		parent = _item_parent_task(row.source_row)
		rows_with_children.add(row.source_row)
		# Idempotencia de la hija: por referencia guardada o por trazabilidad.
		if row.project_task and frappe.db.exists("Task", row.project_task):
			task_name = row.project_task
			counters["tasks_skipped"] += 1
		else:
			existing_child = frappe.db.get_value(
				"Task", {"project": project.name, "source_quotation_scope_item": row.name}, "name"
			)
			if existing_child:
				frappe.db.set_value(
					"Quotation Scope Item", row.name, "project_task", existing_child, update_modified=False
				)
				task_name = existing_child
				counters["tasks_skipped"] += 1
			else:
				subject = _scope_task_subject(row, _purchase_code)
				desc_parts = []
				if row.description:
					desc_parts.append(row.description)
				if row.deliverable:
					desc_parts.append(f"<p><strong>Entregable:</strong></p>{row.deliverable}")
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
						"is_milestone": 1 if row.is_milestone else 0,
						"source_quotation": quotation.name,
						"source_quotation_item_row": row.source_row,
						"source_quotation_scope_item": row.name,
					}
				)
				task.insert(ignore_permissions=True)
				counters["tasks_created"] += 1
				frappe.db.set_value(
					"Quotation Scope Item", row.name, "project_task", task.name, update_modified=False
				)
				task_name = task.name

		contracted.append(
			{
				"scope": row.scope_item or row.name,
				"source_row": row.get("source_row"),
				"task": task_name,
				"parent": parent,
				"offset": row.planned_start_offset_days,
				"duration": row.planned_duration_days,
				"milestone": 1 if row.is_milestone else 0,
				"dep_codes": row.dependency_scope_item_codes,
			}
		)
		if row.scope_item and task_name:
			task_by_row_scope[(row.get("source_row"), row.scope_item)] = task_name
			task_by_scope_all.setdefault(row.scope_item, []).append(task_name)

	# ── Task operativa inicial: ocurrencia VENDIDA sin ninguna hija de scope ejecutable ──
	# Una Task hija operativa bajo el padre-Item, SIN crear Scope Items artificiales. No aplica a Required
	# (los insumos internos no generan padre). Idempotente por (project, source_quotation_item_row, is_group=0).
	for src in occ_rows:
		if src["source_type"] != "sold" or src["source_row"] in rows_with_children:
			continue
		parent = _item_parent_task(src["source_row"])
		if frappe.db.get_value(
			"Task",
			{"project": project.name, "source_quotation_item_row": src["source_row"], "is_group": 0},
			"name",
		):
			counters["tasks_skipped"] += 1
			continue
		item_name, _q, _u = _origin_display(frappe._dict(src))
		frappe.get_doc(
			{
				"doctype": "Task",
				"subject": _("Entregar") + f" — {item_name or src['item_code']}",
				"project": project.name,
				"parent_task": parent,
				"is_group": 0,
				"expected_time": 0,
				"status": "Open",
				"source_quotation": quotation.name,
				"source_quotation_item_row": src["source_row"],
			}
		).insert(ignore_permissions=True)
		counters["tasks_created"] += 1

	# ── 2º paso idempotente: dependencias nativas (Task.depends_on / Task Depends On) ──
	dep_edges = _resolve_native_dependencies(contracted, task_by_row_scope, task_by_scope_all, counters)

	# ── Programación de fechas (offset o propagación por predecesoras) ──
	undatable = _schedule_tasks(project, contracted, dep_edges)

	# ── Rango de cada Task padre (envelope de sus hijas) + rango del Project ──
	_rollup_parent_dates(contracted, project)

	return {
		"project": project.name,
		"parent_tasks_created": counters["parent_created"],
		"parent_tasks_reused": counters["parent_reused"],
		"tasks_created": counters["tasks_created"],
		"tasks_skipped": counters["tasks_skipped"],
		"dependencies_created": counters.get("deps_created", 0),
		"dependencies_ambiguous": counters.get("deps_ambiguous", 0),
		# Tasks realmente no fechables (sin offset y sin predecesora con fecha): no se inventan fechas.
		"undatable_tasks": undatable,
		# Project Type inferido desde paquetes (issue #55); None si ningún paquete lo declara.
		"project_type": project.get("project_type"),
	}


def apply_addendum_to_project(quotation: str, project: str) -> dict:
	"""Aplica una **addenda canónica Ganada** a un Project **existente** (apply-split, ADR-0019 §7.1).

	**Fase 1 — SIEMPRE:** asocia `proposal_project` y sincroniza la economía autorizada del Project. Se
	ejecuta para toda addenda válida y Ganada, aunque NO tenga scope ejecutable (económica-only, costo
	absorbido, solo Required, delta $0 o puramente contractual). **Fase 2 — SOLO si hay scope ejecutable**
	(`include_in_proposal` O `is_internal_cost_task`): valida y materializa los Scope Items como Tasks
	(reuse + dedup). Sin scope ejecutable: la addenda queda correctamente aplicada con 0 Tasks (no se
	inventan Tasks).

	Contrato consumido por `pmo` Change Control (ADR-0005) vía `frappe.get_attr` — **server-side, NO
	whitelisted** (PMO no lo llama por HTTP). Garantía estructural: **nunca crea un Project** (llama a la
	primitive sobre un Project ya resuelto). **NO** hace commit: es atómico con la transacción externa del
	request de PMO (un fallo en cualquier fase revierte asociación + sync + materialización juntas).

	Autoridades separadas: la Quotation `Ganada` aporta la autoridad **comercial** (validada por
	`assert_can_create_project`: submitted + Ganada + no superseded + single-live del grupo); el permiso
	`write` sobre el Project destino aporta la autoridad **operacional** (con `pmo` instalado, sus hooks P4
	lo vuelven owner-only, sin que `erpnext_proposals` dependa de `pmo`). No se exige Proposals Manager.

	Devuelve el mismo resumen (dict) que la materialización. Lanza `frappe.throw`/`PermissionError` en
	fallo; PMO propaga la excepción y NO marca el CR como aplicado."""
	from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import assert_can_create_project

	if not project or not frappe.db.exists("Project", project):
		frappe.throw(_("El Project destino ({0}) no existe.").format(project or "—"))
	project_doc = frappe.get_doc("Project", project)
	# Autoridad operacional: escritura efectiva sobre el Project destino (con pmo, P4 => owner-only).
	project_doc.check_permission("write")

	quotation_doc = frappe.get_doc("Quotation", quotation)
	# Autoridad comercial + invariantes de versión (reutilizado, sin duplicar guards). Para una addenda,
	# `assert_can_create_project` valida single-live DENTRO de su propio grupo ROOT-ADD-NN: ADD-01 y ADD-02
	# son grupos/versionados independientes.
	assert_can_create_project(quotation_doc)

	# Semántica de addenda (contrato canónico, centralizado en utils.addendum): si la Quotation pertenece
	# al namespace -ADD-NN, el Project destino NO es arbitrario. Se deriva el ROOT, se resuelve el Project
	# desde la propuesta raíz Ganada vigente (nunca por nombre) y DEBE coincidir exactamente con el `project`
	# recibido. Una addenda nunca crea Project (esta primitive no tiene rama de creación).
	from erpnext_proposals.erpnext_proposals.utils.addendum import (
		is_addendum_group,
		resolve_root_group,
		resolve_root_project,
	)

	# Opción A (contrato económico): SOLO addendas canónicas «ROOT-ADD-NN» pueden aplicarse a un Project
	# existente. Una propuesta de grupo normal nunca es un "cambio" aplicable → el modelo queda por
	# construcción «1 Project = 1 raíz + N addendas», que hace válido el invariante de root única.
	if not is_addendum_group(quotation_doc.proposal_group):
		frappe.throw(
			_(
				"apply_addendum_to_project solo acepta addendas canónicas «ROOT-ADD-NN». Una Cotización de "
				"grupo normal ({0}) no puede aplicarse a un Project existente."
			).format(quotation_doc.proposal_group)
		)
	root = resolve_root_group(quotation_doc.proposal_group)
	resolved_project = resolve_root_project(root)
	if project != resolved_project:
		frappe.throw(
			_(
				"El Project recibido ({0}) no coincide con el Project de la propuesta raíz ({1}). "
				"Una addenda solo puede aplicarse al Project de su grupo raíz."
			).format(project, resolved_project)
		)

	# Coherencia con el Project destino (invariantes que la creación garantiza por construcción).
	if quotation_doc.company != project_doc.company:
		frappe.throw(
			_("La Company de la Cotización ({0}) no coincide con la del Project ({1}).").format(
				quotation_doc.company, project_doc.company
			)
		)
	if quotation_doc.party_name != project_doc.customer:
		frappe.throw(
			_("El Customer de la Cotización ({0}) no coincide con el del Project ({1}).").format(
				quotation_doc.party_name, project_doc.customer
			)
		)
	if quotation_doc.proposal_project and quotation_doc.proposal_project != project:
		frappe.throw(
			_("La Cotización ya está asociada a otro Project ({0}).").format(quotation_doc.proposal_project)
		)

	# ── Apply-split (ADR-0019 §7.1, Change Control v2 B2) ────────────────────────────────────────────
	# Fase 1 — SIEMPRE: asociar + sincronizar economía. Se ejecuta para TODA addenda válida y Ganada,
	# aunque NO tenga scope ejecutable. La asociación se escribe ANTES del sync porque el contrato
	# económico identifica las addendas aplicadas por proposal_project==project: recomputa el autorizado
	# COMPLETO (root + addendas aplicadas) y espeja Project.estimated_costing. Sin commit interno: un fallo
	# aquí (o en la Fase 2) revierte asociación + estimated_costing + Tasks con la transacción externa.
	if not quotation_doc.proposal_project:
		frappe.db.set_value("Quotation", quotation, "proposal_project", project, update_modified=False)
	from erpnext_proposals.erpnext_proposals.utils.project_economics import sync_project_authorized_cost

	sync_project_authorized_cost(project)

	# Fase 2 — SOLO si la addenda aporta TRABAJO NUEVO, con el MISMO criterio que la creación del root:
	# ≥1 Item vendido (→ padre-Item + Task operativa si no trae Scope) o ≥1 fila ejecutable (→ Tasks de
	# Scope). Una addenda **exclusivamente económica** (sin Items vendidos: solo Required / delta $0 /
	# contractual) queda aplicada con 0 Tasks. Una licencia nueva NO es un ajuste económico. La addenda es
	# DELTA (no re-enuncia el alcance de la raíz) → sin padres duplicados.
	has_new_work = bool(quotation_doc.get("items")) or any(
		r.include_in_proposal or r.is_internal_cost_task for r in quotation_doc.quotation_scope_items
	)
	if has_new_work:
		exec_rows = _validate_scope_for_project(quotation_doc)
		result = _materialize_scope_into_project(quotation_doc, project_doc, exec_rows)
		result["scope_materialized"] = True
		return result

	return {
		"project": project,
		"parent_tasks_created": 0,
		"parent_tasks_reused": 0,
		"tasks_created": 0,
		"tasks_skipped": 0,
		"dependencies_created": 0,
		"dependencies_ambiguous": 0,
		"undatable_tasks": [],
		"project_type": project_doc.get("project_type"),
		"scope_materialized": False,
	}


def _resolve_native_dependencies(
	contracted: list, task_by_row_scope: dict, task_by_scope_all: dict, counters: dict
) -> dict:
	"""Traduce los códigos congelados en dependencias nativas Task.depends_on. Idempotente y **por
	OCURRENCIA** (Tema 1):

	1. Resuelve el predecesor dentro de la MISMA fila origen (misma ocurrencia comercial): si el Scope Item
	   dependiente y su predecesor provienen de la misma ocurrencia, se enlaza `S1@fila → S2@fila`.
	2. Si no hay materialización del predecesor en esa ocurrencia pero el predecesor es **único** en toda la
	   propuesta, se usa esa única materialización (caso no repetido / intra-item de una sola ocurrencia).
	3. Si el predecesor tiene **varias** materializaciones y ninguna en la ocurrencia actual (dependencia
	   cross-ocurrencia ambigua), **NO** se elige arbitrariamente (se elimina el last-wins) → se omite y se
	   cuenta en `deps_ambiguous`. No se inventa una regla cross-item.

	- Solo crea la relación si AMBAS Tasks existen dentro del mismo Project (predecesora contratada).
	- Omite predecesores no contratados y evita duplicar relaciones existentes.
	- Valida ciclos sobre el subgrafo contratado antes de escribir (rollback si hay ciclo).
	Devuelve el grafo {task_sucesora: set(task_predecesora)} para la etapa de programación.
	"""
	dep_edges: dict = {}
	ambiguous = 0
	for node in contracted:
		task = node["task"]
		src_row = node.get("source_row")
		for pcode in _parse_dep_codes(node["dep_codes"]):
			ptask = task_by_row_scope.get((src_row, pcode))  # 1) misma ocurrencia
			if not ptask:
				cands = task_by_scope_all.get(pcode, [])
				if len(cands) == 1:
					ptask = cands[0]  # 2) predecesor único → sin ambigüedad
				elif len(cands) > 1:
					ambiguous += 1  # 3) cross-ocurrencia ambiguo → no inventar; omitir
					continue
			if not ptask or ptask == task:  # no contratada o auto-referencia → omitir
				continue
			dep_edges.setdefault(task, set()).add(ptask)

	_assert_no_task_cycle(dep_edges, [n["task"] for n in contracted])

	created = 0
	for stask, ptasks in dep_edges.items():
		existing = set(
			frappe.get_all("Task Depends On", filters={"parenttype": "Task", "parent": stask}, pluck="task")
		)
		to_add = ptasks - existing
		if not to_add:
			continue
		doc = frappe.get_doc("Task", stask)
		for pt in sorted(to_add):
			doc.append("depends_on", {"task": pt})
		doc.save(ignore_permissions=True)
		created += len(to_add)
	counters["deps_created"] = created
	counters["deps_ambiguous"] = ambiguous
	return dep_edges


def _assert_no_task_cycle(dep_edges: dict, all_tasks: list) -> None:
	"""Kahn sobre el subgrafo contratado. Si no se pueden ordenar todos los nodos → hay ciclo."""
	nodes = set(all_tasks)
	preds = {t: set(dep_edges.get(t, set())) & nodes for t in nodes}
	indeg = {t: len(preds[t]) for t in nodes}
	succ: dict = {t: [] for t in nodes}
	for t, ps in preds.items():
		for p in ps:
			succ[p].append(t)
	queue = [t for t in nodes if indeg[t] == 0]
	seen = 0
	while queue:
		t = queue.pop()
		seen += 1
		for s in succ[t]:
			indeg[s] -= 1
			if indeg[s] == 0:
				queue.append(s)
	if seen != len(nodes):
		frappe.throw(
			_("Dependencia cíclica entre Tasks del Proyecto: no se puede programar. Revise el catálogo.")
		)


def _topo_order(tasks: list, preds: dict) -> list:
	"""Orden topológico (Kahn) para procesar cada Task después de sus predecesoras contratadas."""
	indeg = {t: len(preds[t]) for t in tasks}
	succ: dict = {t: [] for t in tasks}
	for t, ps in preds.items():
		for p in ps:
			succ[p].append(t)
	queue = [t for t in tasks if indeg[t] == 0]
	order = []
	while queue:
		t = queue.pop(0)
		order.append(t)
		for s in succ[t]:
			indeg[s] -= 1
			if indeg[s] == 0:
				queue.append(s)
	return order


def _schedule_tasks(project, contracted: list, dep_edges: dict) -> list:
	"""Programa exp_start_date/exp_end_date por Task. Orden (por diseño):

	1. Offset EXPLÍCITO (Data no vacío, incluye '0') → fecha = Project.expected_start_date + offset
	   (admite negativos). '0' inicia en la fecha de inicio del proyecto.
	2. Sin offset pero con predecesoras fechadas → inicio = día siguiente al fin más tardío de ellas
	   (el orden topológico repite la resolución por dependencias hasta no poder calcular más).
	3. Sin offset y sin predecesora fechada → sin fechas (no se inventan); se reporta.

	Vacío y '0' son distintos: vacío = sin offset (regla 2/3); '0' = inicio explícito (regla 1).

	Fin: hito -> exp_end_date = exp_start_date; normal con duracion -> inicio + max(dur,1) - 1;
	con inicio pero sin duración → mismo día (mínimo determinista para encadenar sucesoras).
	"""
	nodes = {n["task"]: n for n in contracted}
	preds = {t: set(dep_edges.get(t, set())) & set(nodes) for t in nodes}
	project_start = getdate(project.expected_start_date) if project.expected_start_date else None

	start_by_task: dict = {}
	end_by_task: dict = {}
	undatable: list = []

	for task in _topo_order(list(nodes), preds):
		node = nodes[task]
		offset = _offset_value(node["offset"])
		start = None
		if offset is not None and project_start is not None:
			# 1) Offset explícito (incluye '0') → fecha de inicio del proyecto + offset.
			start = add_days(project_start, offset)
		elif offset is None:
			# 2) Sin offset → día siguiente al fin más tardío de sus predecesoras YA fechadas.
			#    El orden topológico garantiza que las predecesoras contratadas ya se resolvieron
			#    (equivale a repetir la resolución por dependencias hasta no poder calcular más).
			pred_ends = [end_by_task[p] for p in preds[task] if end_by_task.get(p)]
			if pred_ends:
				start = add_days(max(pred_ends), 1)

		if start is None:
			# 4) Ni offset explícito ni predecesora fechada → sin fechas; se reporta.
			undatable.append({"task": task, "subject": node["scope"]})
			continue

		start = getdate(start)
		if node["milestone"]:
			end = start
		elif node["duration"]:
			end = add_days(start, max(int(node["duration"]), 1) - 1)
		else:
			end = start  # inicio conocido sin duración → 1 día calendario (determinista)
		end = getdate(end)

		start_by_task[task] = start
		end_by_task[task] = end
		frappe.db.set_value(
			"Task",
			task,
			{"exp_start_date": start, "exp_end_date": end, "is_milestone": 1 if node["milestone"] else 0},
			update_modified=False,
		)

	# Guardar en el nodo para el roll-up de padres.
	for node in contracted:
		node["_start"] = start_by_task.get(node["task"])
		node["_end"] = end_by_task.get(node["task"])
	return undatable


def _rollup_parent_dates(contracted: list, project) -> None:
	"""Rango de cada Task padre (por Item) = **envelope real de sus Tasks hijas** (inicio = `min(inicio de
	hijas fechadas)`, fin = `max(fin de hijas fechadas)`). NO usa una duración configurada ni un segundo
	scheduler: la ventana se deriva únicamente de las fechas ya calculadas de las hijas. Una fase sin hijas
	fechadas **no** recibe fechas (no se inventan).

	Además fija el **fin del Project** (`expected_end_date`) como el fin más tardío del plan, de modo que el
	rango del Project contenga todas las fases/Tasks generadas. El inicio del Project se mantiene como su
	ancla (`expected_start_date` = fecha de la Cotización), que es la base de los offsets y ≤ el inicio de
	cualquier hija con offset ≥ 0.
	"""
	by_parent: dict = {}
	all_ends: list = []
	for node in contracted:
		if node.get("_end"):
			all_ends.append(node["_end"])
		if node.get("parent"):
			by_parent.setdefault(node["parent"], []).append(node)
	for parent, children in by_parent.items():
		starts = [c["_start"] for c in children if c.get("_start")]
		ends = [c["_end"] for c in children if c.get("_end")]
		if starts and ends:
			frappe.db.set_value(
				"Task",
				parent,
				{"exp_start_date": min(starts), "exp_end_date": max(ends)},
				update_modified=False,
			)
	# Fin del Project = fin más tardío del plan (contiene todas las fases). Solo si hay fechas.
	if all_ends:
		frappe.db.set_value(
			"Project", project.name, {"expected_end_date": max(all_ends)}, update_modified=False
		)
