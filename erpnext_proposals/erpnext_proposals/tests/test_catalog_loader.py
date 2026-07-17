"""Tests del loader genérico de catálogos (catalog_loader) con el catálogo de ejemplo ficticio.

Cubre: dry_run sin escrituras, carga real, idempotencia, update_content, conflictos y que las
Sections base no se creen/modifiquen. No usa datos de ningún cliente.
"""

import json
import unittest

import frappe

from erpnext_proposals.erpnext_proposals.catalog_data import catalog_loader

DEMO_PHASES = ["INICIO_DEMO", "CIERRE_DEMO"]
DEMO_SECTIONS = ["Presentación Demo", "Alcance Demo"]
DEMO_TEMPLATE = "Plantilla Demo"
DEMO_SCOPE = ["DEMO-ACT-1", "DEMO-PMO"]


def _sample() -> dict:
	with open(catalog_loader.SAMPLE_CATALOG, encoding="utf-8") as fh:
		return json.load(fh)


def _cleanup() -> None:
	for c in DEMO_SCOPE:
		if frappe.db.exists("Scope Item", c):
			frappe.delete_doc("Scope Item", c, force=True, ignore_permissions=True)
	if frappe.db.exists("Proposal Template", DEMO_TEMPLATE):
		frappe.delete_doc("Proposal Template", DEMO_TEMPLATE, force=True, ignore_permissions=True)
	for s in DEMO_SECTIONS:
		if frappe.db.exists("Proposal Section", s):
			frappe.delete_doc("Proposal Section", s, force=True, ignore_permissions=True)
	for p in DEMO_PHASES:
		if frappe.db.exists("Proposal Phase", p):
			frappe.delete_doc("Proposal Phase", p, force=True, ignore_permissions=True)
	frappe.db.commit()  # nosemgrep — limpieza de fixtures de test


class TestCatalogLoader(unittest.TestCase):
	def tearDown(self):
		_cleanup()

	def test_dry_run_no_escribe(self):
		rep = catalog_loader.run(dry_run=True)
		self.assertTrue(rep["created"], "dry-run debe reportar registros por crear")
		self.assertFalse(frappe.db.exists("Proposal Phase", "INICIO_DEMO"))
		self.assertFalse(frappe.db.exists("Scope Item", "DEMO-ACT-1"))
		self.assertFalse(frappe.db.exists("Proposal Template", DEMO_TEMPLATE))

	def test_carga_real_e_idempotencia(self):
		catalog_loader.run(dry_run=False)
		self.assertTrue(frappe.db.exists("Proposal Phase", "INICIO_DEMO"))
		self.assertTrue(frappe.db.exists("Proposal Section", "Presentación Demo"))
		self.assertTrue(frappe.db.exists("Proposal Template", DEMO_TEMPLATE))
		self.assertEqual(int(frappe.db.get_value("Scope Item", "DEMO-PMO", "is_internal_cost_task")), 1)
		# 2a corrida → idempotente
		rep2 = catalog_loader.run(dry_run=False)
		self.assertEqual(len(rep2["created"]), 0)
		self.assertEqual(len(rep2["updated"]), 0)
		self.assertEqual(len(rep2["conflicts"]), 0)

	def test_conflicto_sin_update_content(self):
		catalog_loader.run(dry_run=False)
		frappe.db.set_value("Proposal Section", "Presentación Demo", "content", "<p>modificado</p>")
		rep = catalog_loader.run(dry_run=False, update_content=False)
		self.assertTrue(any("Presentación Demo" in c for c in rep["conflicts"]))
		self.assertEqual(
			frappe.db.get_value("Proposal Section", "Presentación Demo", "content"), "<p>modificado</p>"
		)

	def test_update_content_restaura(self):
		catalog_loader.run(dry_run=False)
		frappe.db.set_value("Proposal Section", "Presentación Demo", "content", "<p>modificado</p>")
		rep = catalog_loader.run(dry_run=False, update_content=True)
		self.assertTrue(any("Presentación Demo" in u for u in rep["updated"]))
		self.assertIn(
			"{{ doc.customer_name }}",
			frappe.db.get_value("Proposal Section", "Presentación Demo", "content"),
		)

	def test_no_crea_sections_base(self):
		# el catálogo de ejemplo no incluye ninguna de las 10 Sections base
		nombres = {s["section_name"] for s in _sample()["sections"]}
		self.assertFalse(nombres & catalog_loader.BASE_SECTIONS)
