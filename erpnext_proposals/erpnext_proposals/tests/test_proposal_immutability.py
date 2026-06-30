"""
Inmutabilidad de la propuesta completa.

Regla funcional: desde que una Quotation/propuesta queda submitted y congelada,
ningún dato vendido puede modificarse vía la capa de documento (UI/API). Cualquier
ajuste debe hacerse creando una NUEVA versión explícita.

Cubre los gaps no testeados por test_frozen_quotation_integrity (que solo prueba la
tarifa) ni test_proposal_versioning (que prueba el flujo de versión):

  - cabecera congelada (proposal_title, proposal_template, ...)
  - alcance congelado (todos los campos de Quotation Scope Item)
  - estructura de la tabla de alcance (no add / no remove)
  - narrativa congelada (proposal_sections_snapshot; cambios en el catálogo no
    alteran la propuesta ya congelada ni su PDF)
  - resultado histórico: tras cada rechazo, la Quotation conserva los valores originales

El flujo de versionado y el catálogo Proposal Phase se cubren en
test_proposal_versioning.py y doctype/proposal_phase/test_proposal_phase.py.

Límite explícito (documentado, no testeado como garantía): un frappe.db.set_value
crudo / SQL / herramientas admin evade el ciclo del Document — ver
test_frozen_quotation_integrity.test_07.

Nota de entorno: el setUpClass crea sus prerequisitos ERPNext (incluido Fiscal Year)
porque someter una Quotation lo requiere. Es setup de prueba (patrón /test-guard),
no toca código de app ni before_tests.
"""

import unittest

import frappe
from frappe.exceptions import UpdateAfterSubmitError

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)

_IMMUTABLE_EXCEPTIONS = (UpdateAfterSubmitError, frappe.exceptions.ValidationError)


class TestProposalImmutability(unittest.TestCase):
	# ── Setup ────────────────────────────────────────────────────────────────

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._setup_masters()
		cls.quotation = cls._make_submitted_proposal()

	@classmethod
	def tearDownClass(cls):
		for attr in ("quotation",):
			doc = getattr(cls, attr, None)
			name = getattr(doc, "name", None)
			if name and frappe.db.exists("Quotation", name):
				try:
					q = frappe.get_doc("Quotation", name)
					if q.docstatus == 1:
						q.flags.ignore_linked_doctypes = True
						q.cancel()
					frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
				except Exception:
					pass
		cleanup_fiscal_year(getattr(cls, "_created_fy", None))
		super().tearDownClass()

	@classmethod
	def _setup_masters(cls):
		cls.company = frappe.db.get_value("Company", {}, "name")
		if not cls.company:
			raise unittest.SkipTest("No Company found on test site.")

		# Fiscal Year — requerido para someter una Quotation (helper común de pruebas)
		cls._created_fy = ensure_current_fiscal_year()

		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		if not cg:
			raise unittest.SkipTest("No Customer Group found.")
		terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or frappe.db.get_value(
			"Territory", {}, "name"
		)

		if not frappe.db.exists("Customer", "_Test Imm Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test Imm Customer",
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test Imm Customer"

		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)

		ig = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or frappe.db.get_value(
			"Item Group", {}, "name"
		)
		if not frappe.db.exists("Item", "_Test Imm Item"):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "_Test Imm Item",
					"item_name": "_Test Imm Item",
					"item_group": ig,
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
		cls.item = "_Test Imm Item"

		cls.cost_center = frappe.db.get_value(
			"Cost Center", {"is_group": 0, "company": cls.company}, "name"
		) or frappe.db.get_value("Cost Center", {"is_group": 0}, "name")

		# Proposal Section + Template (para narrativa congelada)
		if not frappe.db.exists("Proposal Section", "_Test Imm Section"):
			frappe.get_doc(
				{
					"doctype": "Proposal Section",
					"section_name": "_Test Imm Section",
					"title": "Sección de prueba",
					"content": "<p>Contenido original de la sección.</p>",
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		cls.section = "_Test Imm Section"

		if not frappe.db.exists("Proposal Template", "_Test Imm Template"):
			tpl = frappe.get_doc(
				{
					"doctype": "Proposal Template",
					"template_name": "_Test Imm Template",
					"description": "Template para pruebas de inmutabilidad",
				}
			)
			tpl.append("sections", {"proposal_section": cls.section, "sequence": 10, "include_by_default": 1})
			tpl.insert(ignore_permissions=True)
		cls.proposal_template = "_Test Imm Template"

		# Scope Item ligado al Item — para que el auto-copy poble quotation_scope_items
		if not frappe.db.exists("Scope Item", "_TEST_IMM_SCOPE"):
			frappe.get_doc(
				{
					"doctype": "Scope Item",
					"code": "_TEST_IMM_SCOPE",
					"title": "Actividad de prueba",
					"sequence": 10,
					"phase": "Análisis",
					"description": "Descripción original de la actividad.",
					"deliverable": "Entregable original.",
					"estimated_hours": 8,
					"erpnext_item": cls.item,
					"enabled": 1,
					"visible_in_proposal": 1,
				}
			).insert(ignore_permissions=True)
		cls.scope_code = "_TEST_IMM_SCOPE"

	@classmethod
	def _make_submitted_proposal(cls):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": cls.customer,
				"company": cls.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": f"TEST-IMM-{frappe.generate_hash(length=6)}",
				"proposal_template": cls.proposal_template,
				"proposal_title": "Propuesta Inmutable Original",
				"items": [
					{
						"item_code": cls.item,
						"item_name": "_Test Imm Item",
						"qty": 1,
						"rate": 5000,
						"uom": "Nos",
					}
				],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		if cls.cost_center:
			frappe.db.set_value(
				"Quotation", doc.name, "proposal_cost_center", cls.cost_center, update_modified=False
			)
		doc.reload()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		doc.reload()
		return doc

	# ── Helpers ──────────────────────────────────────────────────────────────

	def _fresh(self):
		return frappe.get_doc("Quotation", self.quotation.name)

	def _scope_rows(self, doc=None):
		doc = doc or self._fresh()
		return doc.quotation_scope_items or []

	def _assert_rejected_and_unchanged(self, mutate, fieldpath_check):
		"""mutate(doc) cambia algo en un doc fresco; debe lanzar; tras recargar, intacto."""
		doc = self._fresh()
		mutate(doc)
		with self.assertRaises(_IMMUTABLE_EXCEPTIONS):
			doc.save()
		fresh = self._fresh()
		fieldpath_check(fresh)

	# ── Sanity ────────────────────────────────────────────────────────────────

	def test_00_proposal_is_submitted_with_scope(self):
		doc = self._fresh()
		self.assertEqual(doc.docstatus, 1, "La Quotation debe estar submitted")
		rows = self._scope_rows(doc)
		self.assertTrue(rows, "Debe tener Quotation Scope Items (auto-copiados)")
		# El alcance debe traer datos reales (no filas vacías) — si no, las pruebas de
		# campo congelado serían vacuas.
		self.assertEqual(rows[0].title, "Actividad de prueba")
		self.assertEqual(rows[0].phase, "Análisis")
		# La narrativa debe haberse congelado: si el snapshot está vacío, la prueba de
		# narrativa no probaría nada → lo exigimos explícitamente.
		self.assertTrue(
			(doc.get("proposal_sections_snapshot") or "").strip(),
			"proposal_sections_snapshot debe estar poblado tras el freeze (narrativa congelada)",
		)

	# ── 1. Cabecera congelada ──────────────────────────────────────────────────

	def test_header_proposal_title_frozen(self):
		self._assert_rejected_and_unchanged(
			lambda d: setattr(d, "proposal_title", "TITULO CAMBIADO"),
			lambda d: self.assertEqual(d.proposal_title, "Propuesta Inmutable Original"),
		)

	def test_header_proposal_template_frozen(self):
		self._assert_rejected_and_unchanged(
			lambda d: setattr(d, "proposal_template", ""),
			lambda d: self.assertEqual(d.proposal_template, self.proposal_template),
		)

	# ── 2. Alcance congelado (todos los campos) ────────────────────────────────

	def _assert_scope_field_frozen(self, fieldname, new_value):
		original = self._scope_rows()[0].get(fieldname)
		doc = self._fresh()
		doc.quotation_scope_items[0].set(fieldname, new_value)
		with self.assertRaises(_IMMUTABLE_EXCEPTIONS):
			doc.save()
		fresh_val = self._fresh().quotation_scope_items[0].get(fieldname)
		self.assertEqual(fresh_val, original, f"{fieldname} debe permanecer sin cambios")

	def test_scope_title_frozen(self):
		self._assert_scope_field_frozen("title", "Título cambiado")

	def test_scope_phase_frozen(self):
		self._assert_scope_field_frozen("phase", "Fase cambiada")

	def test_scope_sequence_frozen(self):
		self._assert_scope_field_frozen("sequence", 999)

	def test_scope_estimated_hours_frozen(self):
		self._assert_scope_field_frozen("estimated_hours", 999)

	def test_scope_description_frozen(self):
		self._assert_scope_field_frozen("description", "Descripción cambiada")

	def test_scope_deliverable_frozen(self):
		self._assert_scope_field_frozen("deliverable", "Entregable cambiado")

	def test_scope_activity_type_frozen(self):
		self._assert_scope_field_frozen("activity_type", "X")

	def test_scope_designation_frozen(self):
		self._assert_scope_field_frozen("designation", "X")

	def test_scope_include_in_proposal_frozen(self):
		current = self._scope_rows()[0].include_in_proposal
		self._assert_scope_field_frozen("include_in_proposal", 0 if current else 1)

	# ── 3. Estructura de la tabla ──────────────────────────────────────────────

	def test_scope_cannot_add_row(self):
		n = len(self._scope_rows())
		doc = self._fresh()
		doc.append(
			"quotation_scope_items",
			{"scope_item": self.scope_code, "item_code": self.item, "title": "Nueva", "code": "X"},
		)
		with self.assertRaises(_IMMUTABLE_EXCEPTIONS):
			doc.save()
		self.assertEqual(len(self._scope_rows()), n, "No se deben agregar filas tras submit")

	def test_scope_cannot_remove_row(self):
		n = len(self._scope_rows())
		self.assertGreater(n, 0)
		doc = self._fresh()
		doc.quotation_scope_items = doc.quotation_scope_items[:-1]
		with self.assertRaises(_IMMUTABLE_EXCEPTIONS):
			doc.save()
		self.assertEqual(len(self._scope_rows()), n, "No se deben eliminar filas tras submit")

	# ── 4. Narrativa congelada ─────────────────────────────────────────────────

	def test_section_snapshot_not_affected_by_catalog_change(self):
		"""Cambiar el contenido del Proposal Section maestro no altera la propuesta congelada."""
		snapshot_before = self._fresh().get("proposal_sections_snapshot")
		section = frappe.get_doc("Proposal Section", self.section)
		section.content = "<p>CONTENIDO MODIFICADO EN EL CATÁLOGO.</p>"
		section.save(ignore_permissions=True)
		try:
			snapshot_after = self._fresh().get("proposal_sections_snapshot")
			self.assertEqual(
				snapshot_before,
				snapshot_after,
				"El snapshot de secciones no debe cambiar al editar el Proposal Section maestro",
			)
			if snapshot_after:
				self.assertNotIn("CONTENIDO MODIFICADO EN EL CATÁLOGO", snapshot_after)
		finally:
			section.reload()
			section.content = "<p>Contenido original de la sección.</p>"
			section.save(ignore_permissions=True)

	# ── 5. Resultado histórico (PDF) ───────────────────────────────────────────

	def test_pdf_reflects_frozen_values(self):
		html = frappe.get_print("Quotation", self.quotation.name, print_format="Propuesta Comercial")
		self.assertIn("Propuesta Inmutable Original", html)
