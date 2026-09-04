import json

import frappe
from frappe import _
from frappe.utils import add_days, getdate

from erpnext_proposals.erpnext_proposals.utils.permissions import assert_can_manage_proposals
from erpnext_proposals.erpnext_proposals.utils.phase import phase_label, phase_sequence


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


def _copy_native_tags(src_dt: str, src_dn: str, dst_dt: str, dst_dn: str) -> int:
	"""Copia los Tags NATIVOS de Frappe de un documento a otro con el mecanismo nativo (DocTags).

	Genérico e idempotente: lee ``_user_tags`` del origen y agrega cada Tag al destino mediante
	``DocTags.add`` (verifica pertenencia + ``unique``, así que un reintento no duplica) creando el
	Tag master si falta. NO conoce nombres de Tags ni códigos de línea: copia exactamente lo que el
	origen tenga. Devuelve cuántos Tags tenía el origen (aplicados al destino).
	"""
	from frappe.desk.doctype.tag.tag import DocTags

	src_tags = [t for t in DocTags(src_dt).get_tags(src_dn).split(",") if t]
	if not src_tags:
		return 0
	dst = DocTags(dst_dt)
	for tag in src_tags:
		dst.add(dst_dn, tag)
	return len(src_tags)


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

	# Filas ejecutables: vendibles O internas de costo (participan en costo y Tasks).
	exec_rows = [
		r for r in quotation.quotation_scope_items if r.include_in_proposal or r.is_internal_cost_task
	]
	if not exec_rows:
		frappe.throw(
			_(
				"No hay actividades ejecutables (visibles o internas de costo) en esta propuesta. "
				"Una propuesta de solo licenciamiento no genera Proyecto."
			)
		)

	# Toda fila ejecutable debe tener fase — bloqueo explícito (no se inventa fase ni Task suelta).
	rows_sin_fase = [r for r in exec_rows if not r.phase]
	if rows_sin_fase:
		nombres = ", ".join((r.title or r.code or r.scope_item or "?") for r in rows_sin_fase[:5])
		frappe.throw(
			_(
				"No se puede crear el Proyecto: {0} actividad(es) ejecutable(s) sin fase asignada ({1}). "
				"Asigne una Proposal Phase a todas las actividades ejecutables antes de crear el Proyecto."
			).format(len(rows_sin_fase), nombres)
		)

	# ── Project (idempotente: reutiliza si ya existe) ──────────────────────────
	if quotation.proposal_project and frappe.db.exists("Project", quotation.proposal_project):
		project = frappe.get_doc("Project", quotation.proposal_project)
	else:
		customer = quotation.party_name
		customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
		project_name = quotation.proposal_title or f"{customer_name} — {quotation.proposal_group}"
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
				}
			)
			project.insert(ignore_permissions=True)
		frappe.db.set_value(
			"Quotation", quotation_name, "proposal_project", project.name, update_modified=False
		)

	# ── Tasks jerárquicas: Task-fase (padre, is_group) → Task-hija (Scope Item) ──
	counters = {
		"parent_created": 0,
		"parent_reused": 0,
		"tasks_created": 0,
		"tasks_skipped": 0,
		"parent_tags_applied": 0,
	}
	phase_task_by_code: dict = {}

	def _phase_parent_task(phase_code: str) -> str:
		"""Task-fase: una por (Project, Proposal Phase). Idempotente.

		Tras crear/resolver la Task padre, materializa en ella los Tags NATIVOS de su Proposal Phase
		(mecanismo nativo, idempotente). Solo la Task padre: nunca las Tasks hijas ni otros documentos.
		"""
		if phase_code in phase_task_by_code:
			return phase_task_by_code[phase_code]
		existing = frappe.db.get_value(
			"Task", {"project": project.name, "proposal_phase": phase_code, "is_group": 1}, "name"
		)
		if existing:
			counters["parent_reused"] += 1
			name = existing
		else:
			parent = frappe.get_doc(
				{
					"doctype": "Task",
					"subject": phase_label(phase_code),
					"project": project.name,
					"is_group": 1,
					"expected_time": 0,
					"status": "Open",
					"proposal_phase": phase_code,
					"source_quotation": quotation.name,
				}
			)
			parent.insert(ignore_permissions=True)
			counters["parent_created"] += 1
			name = parent.name
		# Tags nativos Proposal Phase -> Task padre (idempotente; también sincroniza en reintentos).
		counters["parent_tags_applied"] += _copy_native_tags("Proposal Phase", phase_code, "Task", name)
		phase_task_by_code[phase_code] = name
		return name

	# Orden: fases por Proposal Phase.sequence, luego secuencia del scope, luego idx.
	exec_rows.sort(key=lambda r: (phase_sequence(r.phase), r.sequence or 0, r.idx))

	# Nodos contratados con su Task, para los pasos de dependencias y programación. Incluye Tasks
	# reutilizadas de una corrida previa: un reintento completa deps/fechas faltantes sin duplicar.
	contracted: list = []  # [{scope, source_row, task, parent, offset, duration, milestone, dep_codes}]
	# Resolución de dependencias por OCURRENCIA (Tema 1): (source_row, scope_code) -> Task; y todas las
	# materializaciones de cada scope_code, para el fallback único (sin last-wins ni regla cross-item).
	task_by_row_scope: dict = {}
	task_by_scope_all: dict = {}

	for row in exec_rows:
		parent = _phase_parent_task(row.phase)
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
				subject = (
					f"{row.title or row.code} — {row.item_code}" if row.item_code else (row.title or row.code)
				)
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
						"parent_task": parent,
						"is_group": 0,
						"expected_time": row.estimated_hours or 0,
						"description": "".join(desc_parts),
						"status": "Open",
						"is_milestone": 1 if row.is_milestone else 0,
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

	# ── 2º paso idempotente: dependencias nativas (Task.depends_on / Task Depends On) ──
	dep_edges = _resolve_native_dependencies(contracted, task_by_row_scope, task_by_scope_all, counters)

	# ── Programación de fechas (offset o propagación por predecesoras) ──
	undatable = _schedule_tasks(project, contracted, dep_edges)

	# ── Roll-up de fechas de las Task padre de fase (min inicio / max fin de sus hijas) ──
	_rollup_phase_dates(contracted)

	frappe.db.commit()  # nosemgrep

	return {
		"project": project.name,
		"parent_tasks_created": counters["parent_created"],
		"parent_tasks_reused": counters["parent_reused"],
		"parent_tags_applied": counters["parent_tags_applied"],
		"tasks_created": counters["tasks_created"],
		"tasks_skipped": counters["tasks_skipped"],
		"dependencies_created": counters.get("deps_created", 0),
		"dependencies_ambiguous": counters.get("deps_ambiguous", 0),
		# Tasks realmente no fechables (sin offset y sin predecesora con fecha): no se inventan fechas.
		"undatable_tasks": undatable,
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


def _rollup_phase_dates(contracted: list) -> None:
	"""Actualiza cada Task padre de fase con el mínimo inicio y máximo fin de sus hijas fechadas."""
	by_parent: dict = {}
	for node in contracted:
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
