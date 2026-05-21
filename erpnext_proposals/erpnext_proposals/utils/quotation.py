import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime


def on_quotation_before_submit(doc, method=None):
	"""Fallback freeze at submit time for documents without a prior snapshot."""
	freeze_proposal(doc)


def on_quotation_validate(doc, method=None):
	if not doc.proposal_template:
		return
	_generate_scope_items(doc)


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
			],
			order_by="phase asc, sequence asc",
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
					"include_in_proposal": 1,
					"auto_generated": 1,
				},
			)
			existing.add((item.item_code, si.name))


def freeze_proposal(doc) -> None:
	"""Freeze narrative sections and costing rates at the formal review point.

	Called when the proposal transitions Borrador → En Revision.
	Idempotent: if snapshot already exists, does nothing.
	Hard-fails if the snapshot cannot be created — no silent fallback.
	"""
	if doc.proposal_sections_snapshot:
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
		if not row.include_in_proposal:
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
	_attach_pdf(
		doc,
		print_format="Propuesta Comercial",
		filename=f"Propuesta Comercial - {doc.name}",
		is_private=0,
	)
	_attach_pdf(
		doc,
		print_format="Rentabilidad Estimada",
		filename=f"Rentabilidad Estimada - {doc.name}",
		is_private=1,
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
