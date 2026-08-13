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
	# Banderas de alcance: una fila no puede ser vendible E interna a la vez.
	_validate_internal_cost_flags(doc)
	# Print Format comercial: al aplicar/cambiar la plantilla (o si el override está vacío), poblar
	# `proposal_print_format` con el formato de la Proposal Template. Luego validar (Caso F).
	from erpnext_proposals.erpnext_proposals.utils.print_format import (
		sync_proposal_print_format_from_template,
		validate_print_format,
	)

	sync_proposal_print_format_from_template(doc)
	validate_print_format(doc.get("proposal_print_format"))
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


def _generate_scope_items(doc):
	existing = {
		(row.item_code, row.scope_item)
		for row in (doc.quotation_scope_items or [])
		if row.item_code and row.scope_item
	}

	for item in doc.items or []:
		if not item.item_code:
			continue

		scope_items = frappe.get_all(
			"Scope Item",
			filters={"erpnext_item": item.item_code, "enabled": 1},
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
				"visible_in_proposal",
				"is_internal_cost_task",
				"planned_start_offset_days",
				"moment",
				"planned_duration_days",
				"is_milestone",
			],
			order_by="sequence asc",
		)
		dep_codes = _dependency_codes_map([si.name for si in scope_items])

		for si in scope_items:
			if (item.item_code, si.name) in existing:
				continue
			doc.append(
				"quotation_scope_items",
				{
					"scope_item": si.name,
					"item_code": item.item_code,
					"sequence": si.sequence,
					"code": si.code,
					"title": si.title,
					"description": si.description,
					"deliverable": si.deliverable,
					"phase": si.phase,
					"activity_type": si.default_activity_type,
					"designation": si.default_designation,
					"estimated_hours": si.estimated_hours,
					# Valor inicial de include_in_proposal desde el catálogo (visible_in_proposal).
					# Después es propiedad de la propuesta; el resync NO lo sobrescribe.
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
			existing.add((item.item_code, si.name))


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


def _catalog_rows_for_items(item_codes: list) -> dict:
	"""Devuelve los Scope Item de catálogo habilitados para los item_codes dados,
	mapeados a los campos del child, con clave (item_code, scope_item_name)."""
	result: dict = {}
	codes = list({c for c in (item_codes or []) if c})
	if not codes:
		return result
	rows = frappe.get_all(
		"Scope Item",
		filters={"erpnext_item": ["in", codes], "enabled": 1},
		fields=[
			"name",
			"erpnext_item",
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
	dep_codes = _dependency_codes_map([si.name for si in rows])
	for si in rows:
		result[(si.erpnext_item, si.name)] = {
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
			# Solo para el ADD de resync (valor inicial). NO está en _CATALOG_CONTROLLED_FIELDS,
			# por lo que el UPDATE nunca sobrescribe include_in_proposal en filas existentes.
			"include_in_proposal": 1 if si.visible_in_proposal else 0,
		}
	return result


@frappe.whitelist()
def resync_scope_from_catalog(quotation_name: str) -> dict:
	"""Sincroniza explícitamente la tabla de alcance con el catálogo Scope Item.

	Solo disponible en Borrador. Sobre filas ``auto_generated=1``: actualiza los campos
	controlados por catálogo, elimina las que ya no tienen respaldo (Scope Item
	deshabilitado/borrado o Item quitado de la cotización) y agrega combinaciones nuevas.
	Las filas ``auto_generated=0`` (personalizaciones de la propuesta) nunca se tocan.
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

	item_codes = [it.item_code for it in (doc.items or []) if it.item_code]
	catalog = _catalog_rows_for_items(item_codes)

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

	existing = {(r.item_code, r.scope_item) for r in doc.quotation_scope_items}
	added = 0
	for (item_code, scope_name), fields in catalog.items():
		if (item_code, scope_name) in existing:
			continue
		doc.append(
			"quotation_scope_items",
			{
				"scope_item": scope_name,
				"item_code": item_code,
				"auto_generated": 1,
				# include_in_proposal e is_internal_cost_task vienen de `fields` (catálogo).
				**fields,
			},
		)
		added += 1

	# Resync explícito: refresca los cuatro valores del bloque del servicio en TODAS las líneas y
	# regenera el snapshot de Sections desde los maestros actuales (actualiza captured_on).
	_copy_item_proposal_fields(doc, force=True)
	_sync_sections_snapshot(doc, force=True)
	doc.save()
	return {
		"updated": updated,
		"removed": removed,
		"added": added,
		"total": len(doc.quotation_scope_items),
	}


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


def attach_proposal_pdfs(doc) -> None:
	"""Generate and attach PDF snapshots when proposal enters formal review.

	Genera Propuesta Comercial y Rentabilidad Estimada, ambas como ``File`` PRIVADO
	(``is_private=1``): son la evidencia formal de la propuesta y no deben quedar accesibles por URL
	pública. Los usuarios autorizados las abren/descargan normalmente desde los adjuntos de la
	Quotation (Frappe valida el permiso sobre el documento adjunto).
	PDF generation failure is non-blocking but logged with a visible warning.
	The snapshot JSON is the hard protection; the PDF is the evidence artifact.
	"""
	from erpnext_proposals.erpnext_proposals.utils.print_format import resolve_commercial_print_format

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
		from frappe.utils.pdf import get_pdf

		from erpnext_proposals.erpnext_proposals.utils.official_document_protection import (
			INTERNAL_REPLACE_FLAG,
			OFFICIAL_FLAG_FIELD,
		)

		html = frappe.get_print(doc.doctype, doc.name, print_format=print_format)
		pdf_bytes = get_pdf(html)

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
