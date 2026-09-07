# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Issue #39, Fase 1 (2ª acción): notificación por correo al pasar una Quotation a `Ganada`.

Acción **independiente** de la creación del Project. Reutiliza el DocType nativo `Email Template` cuando está
configurado (render con la Quotation como contexto) y `frappe.sendmail` + Email Queue nativo para el envío
(enlazado a la Quotation por `reference_doctype`/`reference_name`, trazabilidad nativa). Sin motor de templates
propio, sin DocType/log/estado/retry propios: la idempotencia se resuelve con el gating por transición real a
`Ganada` (en `workflow_validations`) + `frappe.enqueue(deduplicate=True, job_id=...)`.
"""

import frappe
from frappe import _


def send_won_notification_email(quotation_name: str) -> None:
	"""Job post-commit: envía el correo de propuesta ganada al destino configurado por Company. Guards
	re-chequeados en el job (el estado pudo cambiar entre encolar y ejecutar): solo envía si la Quotation
	sigue `Ganada`, el toggle está ON y hay correo destino. Usa la Email Template si está configurada; si no,
	un fallback simple del app (nunca los defaults técnicos de `sendmail`)."""
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
	subject, message = _render_won_email(quotation, settings.won_notification_email_template)
	frappe.sendmail(
		recipients=[settings.won_notification_email],
		subject=subject,
		message=message,
		reference_doctype="Quotation",
		reference_name=quotation_name,
	)


def _render_won_email(quotation, template_name: str | None) -> tuple[str, str]:
	"""Devuelve (subject, message). Con Email Template válido: usa la **API nativa**
	`Email Template.get_formatted_email(doc)` — que ya elige `response`/`response_html` según `use_html` y
	renderiza `subject`/cuerpo con la Quotation como contexto (campos planos, p. ej. `{{ name }}`), igual que
	el envío nativo por transición de workflow. **No** reproducimos esa lógica (ver issue #62). Sin plantilla:
	fallback simple del app con enlace nativo a la Quotation."""
	if template_name and frappe.db.exists("Email Template", template_name):
		formatted = frappe.get_doc("Email Template", template_name).get_formatted_email(quotation.as_dict())
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
	url = frappe.utils.get_url_to_form("Quotation", quotation.name)
	subject = _("Propuesta ganada: {0}").format(title)
	message = _("La propuesta {0} de {1} ha sido marcada como Ganada.").format(quotation.name, customer_name)
	message += f'<br><a href="{url}">{quotation.name}</a>'
	return subject, message
