# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Ciclo de `proposal_sections_snapshot`.

El snapshot se construye en la generación inicial (Borrador) desde el Template + Proposal Sections,
se conserva literalmente en guardados normales (sin releer maestros ni cambiar captured_on), se
regenera con force en el resync explícito, se copia literal al versionar y es inmutable desde En
Revisión/Submit. Sin datos de cliente ni contenido del catálogo privado.
"""

import json
import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.company import get_test_company
from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.tests.phases import cleanup_test_phases, ensure_test_phases
from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import create_new_proposal_version
from erpnext_proposals.erpnext_proposals.utils.quotation import freeze_proposal, resync_scope_from_catalog

SECTION = "_Test Snap Section"
TEMPLATE = "_Test Snap Template"
ITEM = "_Test Snap Item"
CUSTOMER = "_Test Snap Customer"
ORIGINAL = "<p>Contenido original de la sección.</p>"
SNAP_KEYS = {
	"sequence",
	"title",
	"content",
	"source_section",
	"is_executive_summary",
	"hide_title",
	"captured_on",
}


class TestSectionsSnapshot(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		cls._fy = ensure_current_fiscal_year()
		cls._phases = ensure_test_phases()
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or frappe.db.get_value(
			"Territory", {}, "name"
		)
		if not frappe.db.exists("Customer", CUSTOMER):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": CUSTOMER,
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		ig = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": ITEM,
					"item_group": ig,
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Section", SECTION):
			frappe.get_doc(
				{
					"doctype": "Proposal Section",
					"section_name": SECTION,
					"title": "Sección Snap",
					"content": ORIGINAL,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			t = frappe.get_doc({"doctype": "Proposal Template", "template_name": TEMPLATE})
			t.append("sections", {"proposal_section": SECTION, "sequence": 10, "include_by_default": 1})
			t.insert(ignore_permissions=True)
		cls.cost_center = frappe.db.get_value(
			"Cost Center", {"is_group": 0, "company": cls.company}, "name"
		) or frappe.db.get_value("Cost Center", {"is_group": 0}, "name")
		cls._quotations = []

	@classmethod
	def tearDownClass(cls):
		frappe.db.set_value("Proposal Section", SECTION, "content", ORIGINAL, update_modified=False)
		for n in cls._quotations:
			if frappe.db.exists("Quotation", n):
				try:
					q = frappe.get_doc("Quotation", n)
					if q.docstatus == 1:
						q.flags.ignore_linked_doctypes = True
						q.cancel()
					frappe.delete_doc("Quotation", n, force=True, ignore_permissions=True)
				except Exception:
					pass
		cleanup_test_phases(getattr(cls, "_phases", None))
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		super().tearDownClass()

	# ── helpers ──────────────────────────────────────────────────────────────

	def _make_draft(self, title="Snap"):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": CUSTOMER,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": f"SNAP-{frappe.generate_hash(length=8)}",
				"proposal_template": TEMPLATE,
				"proposal_title": title,
				"proposal_cost_center": self.cost_center,
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self._quotations.append(doc.name)
		return doc

	def _raw(self, name):
		return frappe.db.get_value("Quotation", name, "proposal_sections_snapshot")

	def _snap(self, name):
		raw = self._raw(name)
		return json.loads(raw) if raw else []

	def _set_section(self, content):
		frappe.db.set_value("Proposal Section", SECTION, "content", content, update_modified=False)
		frappe.clear_document_cache("Proposal Section", SECTION)

	def _set_template_hide_title(self, val):
		"""Marca hide_title en la (única) fila de Proposal Template Section del template de prueba."""
		t = frappe.get_doc("Proposal Template", TEMPLATE)
		t.sections[0].hide_title = int(val)
		t.save(ignore_permissions=True)
		frappe.clear_document_cache("Proposal Template", TEMPLATE)

	# ── 1-2: generación inicial ────────────────────────────────────────────────

	def test_01_generation_builds_snapshot_with_structure(self):
		q = self._make_draft()
		snap = self._snap(q.name)
		self.assertTrue(snap, "Un Borrador nuevo con template debe obtener snapshot")
		self.assertEqual(set(snap[0].keys()), SNAP_KEYS, "Estructura de entrada exacta")
		self.assertEqual(snap[0]["source_section"], SECTION)
		self.assertIn("Contenido original", snap[0]["content"])
		self.assertEqual([s["sequence"] for s in snap], sorted(s["sequence"] for s in snap))

	# ── 3-4: guardado normal ───────────────────────────────────────────────────

	def test_02_normal_save_preserves_snapshot_and_ignores_master(self):
		q = self._make_draft()
		before = self._raw(q.name)
		cap_before = self._snap(q.name)[0]["captured_on"]
		self._set_section("<p>CONTENIDO MAESTRO CAMBIADO.</p>")
		try:
			frappe.get_doc("Quotation", q.name).save(ignore_permissions=True)
			after = self._raw(q.name)
			self.assertEqual(before, after, "Un guardado normal no debe regenerar el snapshot")
			self.assertEqual(self._snap(q.name)[0]["captured_on"], cap_before, "captured_on no cambia")
			self.assertIn("Contenido original", after, "El snapshot conserva el contenido capturado")
		finally:
			self._set_section(ORIGINAL)

	# ── 5-6-7: resync ──────────────────────────────────────────────────────────

	def test_03_resync_regenerates_and_updates_captured_on(self):
		q = self._make_draft()
		cap_before = self._snap(q.name)[0]["captured_on"]
		self._set_section("<p>NUEVO CONTENIDO POR RESYNC.</p>")
		try:
			resync_scope_from_catalog(q.name)
			snap = self._snap(q.name)
			self.assertIn("NUEVO CONTENIDO POR RESYNC", snap[0]["content"], "resync regenera desde maestros")
			self.assertNotEqual(snap[0]["captured_on"], cap_before, "resync actualiza captured_on")
		finally:
			self._set_section(ORIGINAL)

	def test_04_resync_blocked_outside_draft(self):
		q = self._make_draft()
		doc = frappe.get_doc("Quotation", q.name)
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		with self.assertRaises(frappe.exceptions.ValidationError):
			resync_scope_from_catalog(q.name)

	# ── 8-11: nueva versión ────────────────────────────────────────────────────

	def test_05_new_version_copies_snapshot_literally(self):
		q = self._make_draft()
		orig_raw = self._raw(q.name)
		orig_cap = self._snap(q.name)[0]["captured_on"]
		doc = frappe.get_doc("Quotation", q.name)
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		frappe.db.set_value("Quotation", q.name, "workflow_state", "Rechazada", update_modified=False)
		self._set_section("<p>CAMBIO MAESTRO ANTES DE VERSIONAR.</p>")
		try:
			v2 = create_new_proposal_version(q.name, reason="copia snapshot")
			self._quotations.append(v2)
			v2_raw = self._raw(v2)
			self.assertEqual(v2_raw, orig_raw, "La versión copia el snapshot LITERAL")
			self.assertEqual(self._snap(v2)[0]["captured_on"], orig_cap, "Conserva el mismo captured_on")
			self.assertIn("Contenido original", v2_raw, "No toma cambios posteriores del maestro")
			frappe.get_doc("Quotation", v2).save(ignore_permissions=True)  # primer guardado
			self.assertEqual(self._raw(v2), orig_raw, "El primer guardado de la versión no regenera")
		finally:
			self._set_section(ORIGINAL)

	# ── 12-14: freeze / submit ─────────────────────────────────────────────────

	def test_06_freeze_preserves_existing_snapshot(self):
		q = self._make_draft()
		before = self._raw(q.name)
		doc = frappe.get_doc("Quotation", q.name)
		freeze_proposal(doc)
		self.assertEqual(doc.proposal_sections_snapshot, before, "freeze conserva el snapshot existente")

	def test_07_freeze_builds_for_legacy_without_snapshot(self):
		q = self._make_draft()
		frappe.db.set_value("Quotation", q.name, "proposal_sections_snapshot", None, update_modified=False)
		doc = frappe.get_doc("Quotation", q.name)
		self.assertFalse((doc.proposal_sections_snapshot or "").strip())
		freeze_proposal(doc)
		snap = json.loads(doc.proposal_sections_snapshot)
		self.assertTrue(snap, "freeze crea el snapshot para un Draft legacy sin él")
		self.assertEqual(snap[0]["source_section"], SECTION)

	def test_08_submit_preserves_snapshot(self):
		q = self._make_draft()
		before = self._raw(q.name)
		doc = frappe.get_doc("Quotation", q.name)
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		self.assertEqual(self._raw(q.name), before, "Submit conserva el snapshot existente")

	# ── hide_title (presentación por Template) ─────────────────────────────────

	def test_09_hide_title_default_zero(self):
		q = self._make_draft()
		snap = self._snap(q.name)
		self.assertIn("hide_title", snap[0], "La entrada del snapshot incluye hide_title")
		self.assertEqual(snap[0]["hide_title"], 0, "Sin marcar en el Template → hide_title=0")

	def test_10_hide_title_captured_from_template_section(self):
		self._set_template_hide_title(1)
		try:
			q = self._make_draft()
			self.assertEqual(
				self._snap(q.name)[0]["hide_title"], 1, "hide_title se congela desde la fila del Template"
			)
		finally:
			self._set_template_hide_title(0)

	def test_11_version_copies_hide_title_literally(self):
		self._set_template_hide_title(1)
		try:
			q = self._make_draft()
			self.assertEqual(self._snap(q.name)[0]["hide_title"], 1)
			doc = frappe.get_doc("Quotation", q.name)
			doc.flags.ignore_mandatory = True
			doc.flags.ignore_links = True
			doc.submit()
			frappe.db.set_value("Quotation", q.name, "workflow_state", "Rechazada", update_modified=False)
			# cambiar el Template DESPUÉS de versionar no debe afectar la copia literal
			self._set_template_hide_title(0)
			v2 = create_new_proposal_version(q.name, reason="hide_title literal")
			self._quotations.append(v2)
			self.assertEqual(
				self._snap(v2)[0]["hide_title"],
				1,
				"La versión copia hide_title literal (no relee el Template)",
			)
		finally:
			self._set_template_hide_title(0)

	def test_12_resync_updates_hide_title_in_draft(self):
		q = self._make_draft()
		self.assertEqual(self._snap(q.name)[0]["hide_title"], 0)
		self._set_template_hide_title(1)
		try:
			resync_scope_from_catalog(q.name)
			self.assertEqual(
				self._snap(q.name)[0]["hide_title"],
				1,
				"resync en Draft actualiza hide_title desde el Template",
			)
		finally:
			self._set_template_hide_title(0)

	def test_13_hide_title_immutable_after_submit(self):
		q = self._make_draft()
		self.assertEqual(self._snap(q.name)[0]["hide_title"], 0)
		doc = frappe.get_doc("Quotation", q.name)
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		# cambiar el Template tras el submit no altera el snapshot congelado
		self._set_template_hide_title(1)
		try:
			self.assertEqual(
				self._snap(q.name)[0]["hide_title"], 0, "Desde En Revisión/Submit el snapshot es inmutable"
			)
		finally:
			self._set_template_hide_title(0)
