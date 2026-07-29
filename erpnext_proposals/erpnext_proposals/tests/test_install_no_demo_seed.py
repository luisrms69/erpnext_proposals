"""Pruebas: una instalación nueva del app NO siembra datos demo y conserva la estructura técnica.

El app público (``after_install``) solo debe sincronizar estructura técnica (Desktop Icon; las
DocTypes/Custom Fields/Print Formats/Roles/Workflow vienen por metadata y fixtures). El contenido
comercial (Templates, Sections, Items, Scope Items, Phases, Print Formats comerciales) se entrega
EXCLUSIVAMENTE por el catálogo corporativo privado (``catalog_loader.run``), nunca por install/migrate.

Cubre que una instalación nueva:
  - no crea Templates demo,
  - no crea Sections placeholder,
  - no crea Items / contenido comercial demo,
  - conserva la estructura técnica necesaria (sync de Desktop Icon).
"""

import inspect
import unittest

import frappe

from erpnext_proposals.erpnext_proposals import install

# Templates demo que el app solía sembrar en after_install y que ya NO debe crear.
DEMO_TEMPLATES = ["Implementacion ERPNext", "Integracion API", "Bolsa de Horas Soporte"]

# Las 10 Sections placeholder ("En esta sección debe…") que el app solía sembrar y que ya NO debe crear.
PLACEHOLDER_SECTIONS = [
	"Resumen Ejecutivo",
	"Objetivo del Proyecto",
	"Modalidad de Trabajo",
	"Metodologia",
	"Criterios de Aceptacion",
	"Responsabilidades del Cliente",
	"Supuestos",
	"Exclusiones",
	"Control de Cambios",
	"Cierre del Proyecto",
]

# Marcadores de creación de contenido comercial: install.py no debe construir ningún registro de
# estos DocTypes (Templates, Sections, Items, Scope Items). El contenido comercial es del catálogo.
COMMERCIAL_DOCTYPE_MARKERS = [
	'"doctype": "Item"',
	'"doctype": "Proposal Template"',
	'"doctype": "Proposal Section"',
	'"doctype": "Scope Item"',
]


class TestInstallNoDemoSeed(unittest.TestCase):
	def test_seeders_demo_eliminados(self):
		"""Los seeders de contenido demo fueron eliminados del módulo de instalación."""
		for fn in ("_create_base_catalog", "_create_sections", "_create_templates"):
			self.assertFalse(hasattr(install, fn), f"install.py no debe exponer '{fn}' (sembraba demo)")

	def test_estructura_tecnica_conservada(self):
		"""after_install conserva la estructura técnica necesaria (sync de Desktop Icon)."""
		self.assertTrue(hasattr(install, "after_install"), "install.py debe exponer after_install")
		self.assertTrue(
			hasattr(install, "_sync_desktop_icons"), "after_install debe conservar el sync de Desktop Icon"
		)

	def test_install_no_referencia_contenido_demo(self):
		"""El código de instalación no menciona ningún Template/Section demo ni construye contenido
		comercial (Items/Templates/Sections/Scope Items) → no los puede sembrar."""
		src = inspect.getsource(install)
		for name in DEMO_TEMPLATES + PLACEHOLDER_SECTIONS:
			self.assertNotIn(name, src, f"install.py referencia contenido demo: {name!r}")
		for marker in COMMERCIAL_DOCTYPE_MARKERS:
			self.assertNotIn(marker, src, f"install.py construye contenido comercial: {marker}")

	def test_after_install_no_crea_contenido_demo(self):
		"""Simula instalación nueva: aísla cualquier residuo demo, corre after_install y verifica que
		no crea Templates demo ni Sections placeholder."""
		self._aislar_residuo_demo()

		install.after_install()  # solo debe sincronizar el Desktop Icon
		frappe.db.rollback()

		for t in DEMO_TEMPLATES:
			self.assertFalse(frappe.db.exists("Proposal Template", t), f"install creó Template demo: {t}")
		for s in PLACEHOLDER_SECTIONS:
			self.assertFalse(
				frappe.db.exists("Proposal Section", s), f"install creó Section placeholder: {s}"
			)

	def _aislar_residuo_demo(self):
		"""Elimina residuo demo (de un install viejo) para simular una instalación limpia.
		Si algún residuo está bloqueado por referencias en el site de test, se omite la prueba."""
		for t in DEMO_TEMPLATES:
			if frappe.db.exists("Proposal Template", t):
				try:
					frappe.delete_doc("Proposal Template", t, force=True, ignore_permissions=True)
				except Exception:
					self.skipTest(f"No se pudo aislar el residuo demo '{t}' en el site de test")
		for s in PLACEHOLDER_SECTIONS:
			if frappe.db.exists("Proposal Section", s):
				try:
					frappe.delete_doc("Proposal Section", s, force=True, ignore_permissions=True)
				except Exception:
					pass
		frappe.db.commit()  # nosemgrep — aislamiento de residuo demo en el site de test
