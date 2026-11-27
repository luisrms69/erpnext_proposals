# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Issue #39, Fase 1 (2ª acción): notificación por correo al pasar una Quotation a `Ganada`.

Se encadena **tras la creación del Project** (invocada al final de `auto_create_project_on_won`), de modo que
el correo siempre ve el Project ya creado y vinculado. Reutiliza el DocType nativo `Email Template` cuando está
configurado (render con un contexto enriquecido: Quotation + Project + productos + entregables) y
`frappe.sendmail` + Email Queue nativo para el envío (enlazado a la Quotation por
`reference_doctype`/`reference_name`, trazabilidad nativa). Sin motor de templates propio, sin
DocType/log/estado/retry propios: el anti-duplicado se resuelve con el retorno temprano del job de creación
(idempotente) + `frappe.enqueue(deduplicate=True, job_id=...)`.
"""

import frappe
from frappe import _


def send_won_notification_email(quotation_name: str) -> None:
	"""Job post-creación del Project: envía el correo de propuesta ganada al destino configurado por Company.
	Guards re-chequeados en el job (el estado pudo cambiar entre encolar y ejecutar): solo envía si la
	Quotation sigue `Ganada`, el toggle está ON, hay correo destino **y el Project ya está creado y vinculado**
	(`proposal_project`). Este último guard materializa el requisito de orden: el correo nunca se envía antes de
	existir el Project. Usa la Email Template si está configurada; si no, un fallback simple del app (nunca los
	defaults técnicos de `sendmail`)."""
	quotation = frappe.get_doc("Quotation", quotation_name)
	if quotation.get("workflow_state") != "Ganada":
		return
	company = quotation.get("company")
	if not company:
		return
	settings = frappe.db.get_value(
		"Proposal Settings",
		{"company": company},
		["send_won_notification_email", "won_notification_email", "won_notification_email_template"],
		as_dict=True,
	)
	if not settings or not settings.send_won_notification_email or not settings.won_notification_email:
		return
	# Requisito de orden (flujo async): exige Project creado y vinculado antes de notificar.
	project_name = quotation.get("proposal_project")
	if not project_name or not frappe.db.exists("Project", project_name):
		return
	project = frappe.get_doc("Project", project_name)
	subject, message = _render_won_email(quotation, project, settings.won_notification_email_template)
	frappe.sendmail(
		recipients=[settings.won_notification_email],
		subject=subject,
		message=message,
		reference_doctype="Quotation",
		reference_name=quotation_name,
	)


def _build_email_context(quotation, project) -> dict:
	"""Contexto Jinja para la Email Template: la Quotation (`as_dict`, campos planos como `{{ name }}`) más
	datos ya **resueltos en Python** (sin depender de helpers Jinja ni de campos que podrían no existir al
	enviar): cliente, compañía, Proposal Group, productos contratados, Project (id/nombre/enlace) y los
	entregables/actividades del Project (tareas). `get_formatted_email(doc)` renderiza con este dict como
	contexto plano, por lo que todas las claves son referenciables directamente en la plantilla."""
	ctx = quotation.as_dict()
	customer = quotation.get("party_name")
	ctx["customer_display"] = (
		(frappe.db.get_value("Customer", customer, "customer_name") or customer) if customer else "—"
	)
	ctx["company_display"] = quotation.get("company") or "—"
	ctx["proposal_group_display"] = quotation.get("proposal_group") or "—"
	ctx["proposal_title_display"] = quotation.get("proposal_title") or quotation.name
	ctx["quotation_url"] = frappe.utils.get_url_to_form("Quotation", quotation.name)
	ctx["products"] = [
		{"item": (it.get("item_name") or it.get("item_code")), "qty": it.get("qty"), "uom": it.get("uom")}
		for it in (quotation.get("items") or [])
	]
	ctx["project_id"] = project.name
	ctx["project_display"] = project.get("project_name") or project.name
	ctx["project_url"] = frappe.utils.get_url_to_form("Project", project.name)
	# Entregables/actividades: padres (is_group) = entregables por producto; hijas = actividades ejecutables.
	tasks = frappe.get_all(
		"Task",
		filters={"project": project.name},
		fields=["subject", "is_group"],
		order_by="is_group desc, creation asc",
	)
	ctx["workstreams"] = [t.subject for t in tasks if t.is_group]
	ctx["deliverables"] = [t.subject for t in tasks if not t.is_group]
	return ctx


def _render_won_email(quotation, project, template_name: str | None) -> tuple[str, str]:
	"""Devuelve (subject, message). Con Email Template válido: usa la **API nativa**
	`Email Template.get_formatted_email(doc)` — que elige `response`/`response_html` según `use_html` y
	renderiza con el contexto enriquecido (`_build_email_context`). Sin plantilla: fallback simple del app con
	enlaces nativos a la Quotation y al Project."""
	if template_name and frappe.db.exists("Email Template", template_name):
		context = _build_email_context(quotation, project)
		formatted = frappe.get_doc("Email Template", template_name).get_formatted_email(context)
		subject = formatted.get("subject")
		message = formatted.get("message")
		if subject and message:
			return subject, message

	# Fallback simple (nunca "No Subject" / "No Message").
	title = quotation.get("proposal_title") or quotation.name
	customer = quotation.get("party_name")
	customer_name = (
		(frappe.db.get_value("Customer", customer, "customer_name") or customer) if customer else "—"
	)
	q_url = frappe.utils.get_url_to_form("Quotation", quotation.name)
	p_url = frappe.utils.get_url_to_form("Project", project.name)
	project_display = project.get("project_name") or project.name
	subject = _("Propuesta ganada: {0}").format(title)
	message = _("La propuesta {0} de {1} ha sido marcada como Ganada y su Proyecto fue creado.").format(
		quotation.name, customer_name
	)
	message += f'<br><a href="{q_url}">{quotation.name}</a> — <a href="{p_url}">{project_display}</a>'
	return subject, message
