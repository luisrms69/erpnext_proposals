"""
after_install hook for erpnext_proposals.

Creates base catalog (Proposal Sections and Templates) only on first install.
Does NOT run on migrate — never overwrites user customizations.
Also syncs the app Desktop Icon so it appears without a manual sync-desktop-icons step.
"""

import os

import frappe


def after_install():
	_create_base_catalog()
	_sync_desktop_icons()


def _sync_desktop_icons():
	"""Import the app's Desktop Icon on install.

	Replicates the core ``sync-desktop-icons`` command for this app only, so a fresh
	install shows the workspace icon without requiring a separate manual command.
	"""
	from frappe.model.sync import import_file_by_path
	from frappe.modules.utils import get_app_level_directory_path

	directory_path = get_app_level_directory_path("desktop_icon", "erpnext_proposals")
	if not os.path.exists(directory_path):
		return

	for filename in os.listdir(directory_path):
		import_file_by_path(os.path.join(directory_path, filename), force=True, ignore_version=True)

	frappe.db.commit()


def _create_base_catalog():
	_create_sections()
	_create_templates()
	frappe.db.commit()


def _create_sections():
	sections = [
		{
			"section_name": "Resumen Ejecutivo",
			"is_executive_summary": 1,
			"title": "Resumen Ejecutivo",
			"content": "<p>En esta sección debe redactarse un resumen breve de la propuesta. Debe explicar el problema o necesidad del cliente, la solución propuesta, los beneficios esperados, el alcance general y el valor de negocio. Evitar detalles técnicos excesivos. Idealmente debe poder ser leído por dirección en menos de dos minutos.</p>",
		},
		{
			"section_name": "Objetivo del Proyecto",
			"title": "Objetivo del Proyecto",
			"content": "<p>En esta sección debe describirse el objetivo principal del proyecto. Debe indicar qué se busca lograr, qué proceso o necesidad se atenderá, qué resultado esperado tendrá el cliente y cómo se relaciona con el alcance propuesto.</p>",
		},
		{
			"section_name": "Modalidad de Trabajo",
			"title": "Modalidad de Trabajo",
			"content": "<p>En esta sección debe indicarse cómo se prestará el servicio: remoto, presencial o híbrido; horarios base; mecanismos de comunicación; sesiones de trabajo; responsables; y condiciones operativas relevantes.</p>",
		},
		{
			"section_name": "Metodologia",
			"title": "Metodología",
			"content": "<p>En esta sección debe describirse la metodología de ejecución del proyecto. Puede incluir fases como levantamiento, análisis, configuración, desarrollo, validación, capacitación, salida a operación y acompañamiento. Debe explicar cómo se controlarán avances y entregables.</p>",
		},
		{
			"section_name": "Criterios de Aceptacion",
			"title": "Criterios de Aceptación",
			"content": "<p>En esta sección deben definirse las condiciones bajo las cuales los entregables serán considerados aceptados. Debe incluir criterios de validación, evidencia esperada, responsables de revisión y tratamiento de observaciones.</p>",
		},
		{
			"section_name": "Responsabilidades del Cliente",
			"title": "Responsabilidades del Cliente",
			"content": "<p>En esta sección deben describirse las responsabilidades del cliente: entrega de información, accesos, usuarios clave, validaciones, aprobaciones internas, disponibilidad para sesiones y restricciones que puedan impactar el proyecto.</p>",
		},
		{
			"section_name": "Supuestos",
			"title": "Supuestos",
			"content": "<p>En esta sección deben documentarse los supuestos bajo los cuales se preparó la propuesta. Deben incluir condiciones de información disponible, alcance conocido, disponibilidad de usuarios, ambiente técnico, licencias, infraestructura y dependencias externas.</p>",
		},
		{
			"section_name": "Exclusiones",
			"title": "Exclusiones",
			"content": "<p>En esta sección debe aclararse qué no está incluido en la propuesta. Debe mencionar actividades, servicios, licencias, infraestructura, integraciones, migraciones, soporte o desarrollos que solo se realizarán si se cotizan por separado.</p>",
		},
		{
			"section_name": "Control de Cambios",
			"title": "Control de Cambios",
			"content": "<p>En esta sección debe explicarse cómo se manejarán cambios de alcance, nuevas solicitudes, ajustes de prioridad o actividades no contempladas. Debe indicar que cualquier cambio puede impactar costo, tiempo y entregables.</p>",
		},
		{
			"section_name": "Cierre del Proyecto",
			"title": "Cierre del Proyecto",
			"content": "<p>En esta sección debe describirse cómo se cerrará el proyecto: validación final, entrega de evidencias, documentación, observaciones pendientes, recomendaciones y posibles fases futuras.</p>",
		},
	]

	for s in sections:
		if not frappe.db.exists("Proposal Section", s["section_name"]):
			frappe.get_doc({"doctype": "Proposal Section", "enabled": 1, **s}).insert(ignore_permissions=True)


def _create_templates():
	templates = [
		{
			"template_name": "Implementacion ERPNext",
			"description": "Template base para propuestas de implementación, configuración o mejora de procesos sobre ERPNext.",
			"sections": [
				("Resumen Ejecutivo", 10),
				("Objetivo del Proyecto", 20),
				("Modalidad de Trabajo", 30),
				("Metodologia", 40),
				("Criterios de Aceptacion", 50),
				("Responsabilidades del Cliente", 60),
				("Supuestos", 70),
				("Exclusiones", 80),
				("Control de Cambios", 90),
				("Cierre del Proyecto", 100),
			],
		},
		{
			"template_name": "Integracion API",
			"description": "Template base para propuestas de integración técnica, automatización o desarrollo de conectores.",
			"sections": [
				("Resumen Ejecutivo", 10),
				("Objetivo del Proyecto", 20),
				("Modalidad de Trabajo", 30),
				("Metodologia", 40),
				("Criterios de Aceptacion", 50),
				("Responsabilidades del Cliente", 60),
				("Supuestos", 70),
				("Exclusiones", 80),
				("Control de Cambios", 90),
				("Cierre del Proyecto", 100),
			],
		},
		{
			"template_name": "Bolsa de Horas Soporte",
			"description": "Template base para propuestas de soporte, asesoría o bolsa de horas.",
			"sections": [
				("Resumen Ejecutivo", 10),
				("Objetivo del Proyecto", 20),
				("Modalidad de Trabajo", 30),
				("Responsabilidades del Cliente", 40),
				("Supuestos", 50),
				("Exclusiones", 60),
				("Control de Cambios", 70),
				("Cierre del Proyecto", 80),
			],
		},
	]

	for t in templates:
		if frappe.db.exists("Proposal Template", t["template_name"]):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Proposal Template",
				"template_name": t["template_name"],
				"description": t["description"],
			}
		)
		for section_name, seq in t["sections"]:
			if frappe.db.exists("Proposal Section", section_name):
				doc.append(
					"sections",
					{
						"proposal_section": section_name,
						"sequence": seq,
						"include_by_default": 1,
					},
				)
		doc.insert(ignore_permissions=True)
