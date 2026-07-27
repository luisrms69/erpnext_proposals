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
				*_EDITORIAL_FIELDS,
			],
			order_by="sequence asc",
		)

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
					"auto_generated": 1,
					# Campos editoriales opcionales (contenido de propuesta; no afectan Task/costo).
					**{f: si.get(f) for f in _EDITORIAL_FIELDS},
				},
			)
			existing.add((item.item_code, si.name))


# Campos editoriales opcionales del alcance (Text Editor). Se copian del catálogo Scope Item a la
# copia congelada del Quotation Scope Item como contenido de propuesta. NO afectan Tasks, horas ni
# costos. Se administran por catálogo igual que description/deliverable (incluye limpieza con null).
_EDITORIAL_FIELDS = (
	"service_objective",
	"methodology",
	"expected_result",
	"scope_limit",
	"exclusions",
	"acceptance_criteria",
)


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
	*_EDITORIAL_FIELDS,
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
			*_EDITORIAL_FIELDS,
		],
		order_by="sequence asc",
	)
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
			# Solo para el ADD de resync (valor inicial). NO está en _CATALOG_CONTROLLED_FIELDS,
			# por lo que el UPDATE nunca sobrescribe include_in_proposal en filas existentes.
			"include_in_proposal": 1 if si.visible_in_proposal else 0,
			# Campos editoriales opcionales (controlados por catálogo vía _CATALOG_CONTROLLED_FIELDS).
			**{f: si.get(f) for f in _EDITORIAL_FIELDS},
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

	doc.save()
	return {
		"updated": updated,
		"removed": removed,
		"added": added,
		"total": len(doc.quotation_scope_items),
	}


def freeze_proposal(doc) -> None:
	"""Freeze narrative sections and costing rates at the formal review point.

	Called when the proposal transitions Borrador → En Revision.
	Idempotent: if snapshot already exists, does nothing.
	Hard-fails if the snapshot cannot be created — no silent fallback.
	"""
	if not getattr(doc, "proposal_template", None):
		return  # no template — nothing to freeze

	# Congelar el Print Format comercial efectivo (idempotente) — sobrevive incluso si el snapshot ya existe.
	from erpnext_proposals.erpnext_proposals.utils.print_format import freeze_effective_print_format

	freeze_effective_print_format(doc)

	if getattr(doc, "proposal_sections_snapshot", None):
		return  # already frozen — never overwrite

	_freeze_section_content(doc)
	_freeze_costing_rates(doc)


def _freeze_section_content(doc) -> None:
	"""Serialize all template sections to JSON snapshot (raw Jinja, not rendered HTML).

	Hard-fails with frappe.throw if snapshot cannot be created.
	No silent fallback to live catalog in formal states.
	"""
	if not doc.proposal_template:
		return

	try:
		tmpl = frappe.get_doc("Proposal Template", doc.proposal_template)
		snapshot = []
		now = now_datetime().isoformat()

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
					"captured_on": now,
				}
			)

		doc.proposal_sections_snapshot = json.dumps(snapshot, ensure_ascii=False)

	except frappe.exceptions.ValidationError:
		raise  # re-raise frappe.throw calls
	except Exception as e:
		frappe.throw(
			_("No se pudo congelar el contenido de la propuesta: {0}").format(str(e)),
			title=_("Error al congelar propuesta"),
		)


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

	Generates Propuesta Comercial (public) and Rentabilidad Estimada (private).
	PDF generation failure is non-blocking but logged with a visible warning.
	The snapshot JSON is the hard protection; the PDF is the evidence artifact.
	"""
	from erpnext_proposals.erpnext_proposals.utils.print_format import resolve_commercial_print_format

	commercial_pf = resolve_commercial_print_format(doc)
	_attach_pdf(
		doc,
		print_format=commercial_pf,
		filename=f"{commercial_pf} - {doc.name}",
		is_private=0,
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

		html = frappe.get_print(doc.doctype, doc.name, print_format=print_format)
		pdf_bytes = get_pdf(html)

		# Remove previous version of this attachment if it exists
		existing = frappe.db.get_value(
			"File",
			{
				"attached_to_doctype": doc.doctype,
				"attached_to_name": doc.name,
				"file_name": f"{filename}.pdf",
			},
			"name",
		)
		if existing:
			frappe.delete_doc("File", existing, ignore_permissions=True)

		save_file(
			fname=f"{filename}.pdf",
			content=pdf_bytes,
			dt=doc.doctype,
			dn=doc.name,
			is_private=is_private,
		)

	except Exception as e:
		frappe.log_error(f"Error generating PDF '{print_format}' for {doc.name}: {e}")
		frappe.msgprint(
			_(
				"No se pudo generar el PDF '{0}'. El proceso continúa pero revisa los adjuntos manualmente."
			).format(print_format),
			indicator="orange",
			alert=True,
		)
