# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Materialización de Sections narrativas en la child table `proposal_sections` (B2).

Modelo nativo: Proposal Template → materializa filas EFECTIVAS en el Draft → el Draft queda
independiente de los maestros. Cambios posteriores en Proposal Template/Section NO se propagan; solo
la reaplicación explícita (resync) reemplaza las filas. El flujo nuevo NO escribe
`proposal_sections_snapshot`. Sin datos de cliente ni contenido del catálogo privado.
"""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.company import (
	get_test_company,
	get_test_cost_center,
	get_test_item_group,
	get_test_price_list,
)
from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.tests.phases import cleanup_test_phases, ensure_test_phases
from erpnext_proposals.erpnext_proposals.utils.quotation import resync_scope_from_catalog

SECTION = "_Test Mat Section"
SECTION_OUT = "_Test Mat Section Out"  # existe pero NO está en el Template
OPT_SECTION = "_Test Mat Optional"
TEMPLATE = "_Test Mat Template"
ITEM = "_Test Mat Item"
CUSTOMER = "_Test Mat Customer"
ORIGINAL = "<p>Contenido original de la sección.</p>"
OPT_MARK = "CLAUSULA OPCIONAL DE PRUEBA"


class TestProposalSectionsMaterialize(unittest.TestCase):
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
		ig = get_test_item_group()
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
		for name, content in (
			(SECTION, ORIGINAL),
			(SECTION_OUT, "<p>Sección fuera del Template.</p>"),
			(OPT_SECTION, f"<p>{OPT_MARK}</p>"),
		):
			if not frappe.db.exists("Proposal Section", name):
				frappe.get_doc(
					{
						"doctype": "Proposal Section",
						"section_name": name,
						"title": f"Título {name}",
						"content": content,
						"enabled": 1,
					}
				).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			t = frappe.get_doc({"doctype": "Proposal Template", "template_name": TEMPLATE})
			t.append("sections", {"proposal_section": SECTION, "sequence": 10, "include_by_default": 1})
			t.append("sections", {"proposal_section": OPT_SECTION, "sequence": 640, "include_by_default": 0})
			t.insert(ignore_permissions=True)
		cls.cost_center = get_test_cost_center(cls.company)
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

	# ── helpers ────────────────────────────────────────────────────────────────

	def _make_draft(self, title="Mat", select_optional=False):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": CUSTOMER,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": f"MAT-{frappe.generate_hash(length=8)}",
				"proposal_template": TEMPLATE,
				"proposal_title": title,
				"proposal_cost_center": self.cost_center,
				"selling_price_list": get_test_price_list(),
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		if select_optional:
			doc.append("proposal_optional_sections", {"proposal_section": OPT_SECTION})
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self._quotations.append(doc.name)
		return doc

	def _rows(self, name):
		doc = frappe.get_doc("Quotation", name)
		return sorted(
			[r.as_dict() for r in (doc.proposal_sections or [])],
			key=lambda r: r.get("sequence") or 0,
		)

	def _snap_raw(self, name):
		return frappe.db.get_value("Quotation", name, "proposal_sections_snapshot")

	def _set_section(self, content, name=SECTION):
		frappe.db.set_value("Proposal Section", name, "content", content, update_modified=False)
		frappe.clear_document_cache("Proposal Section", name)

	def _set_template_custom_title(self, val):
		t = frappe.get_doc("Proposal Template", TEMPLATE)
		row = next(r for r in t.sections if r.proposal_section == SECTION)
		row.custom_title = val
		t.save(ignore_permissions=True)
		frappe.clear_document_cache("Proposal Template", TEMPLATE)

	# ── 1: generación materializa exactamente el Template ───────────────────────

	def test_01_generation_materializes_template_sections(self):
		q = self._make_draft()
		rows = self._rows(q.name)
		self.assertEqual(len(rows), 1, "Solo la fila base (include_by_default=1) se materializa")
		r = rows[0]
		self.assertEqual(r["proposal_section"], SECTION, "La fila referencia la Proposal Section origen")
		self.assertEqual(r["sequence"], 10, "Conserva la sequence del Template")
		self.assertIn("Contenido original", r["content"], "Copia el contenido efectivo del maestro")
		self.assertEqual(r["hide_title"], 0)

	# ── 2: una Section fuera del Template nunca aparece ─────────────────────────

	def test_02_section_outside_template_absent(self):
		q = self._make_draft()
		refs = [r["proposal_section"] for r in self._rows(q.name)]
		self.assertNotIn(SECTION_OUT, refs, "Una Section fuera del Template no puede aparecer")

	# ── 3: cambiar el maestro Section NO propaga al Draft ───────────────────────

	def test_03_master_section_change_not_propagated(self):
		q = self._make_draft()
		self._set_section("<p>CONTENIDO MAESTRO CAMBIADO.</p>")
		try:
			frappe.get_doc("Quotation", q.name).save(ignore_permissions=True)
			self.assertIn(
				"Contenido original",
				self._rows(q.name)[0]["content"],
				"Un guardado normal no relee el maestro Section",
			)
		finally:
			self._set_section(ORIGINAL)

	# ── 4: cambiar el Template NO propaga al Draft ──────────────────────────────

	def test_04_template_change_not_propagated(self):
		q = self._make_draft()
		self._set_template_custom_title("TÍTULO NUEVO DEL TEMPLATE")
		try:
			frappe.get_doc("Quotation", q.name).save(ignore_permissions=True)
			self.assertNotEqual(
				self._rows(q.name)[0]["title"],
				"TÍTULO NUEVO DEL TEMPLATE",
				"Un guardado normal no relee el Template",
			)
		finally:
			self._set_template_custom_title(None)

	# ── 5: reaplicación explícita (resync) reemplaza las filas ──────────────────

	def test_05_explicit_reapply_replaces_rows(self):
		q = self._make_draft()
		self._set_section("<p>NUEVO CONTENIDO POR REAPLICACIÓN.</p>")
		try:
			resync_scope_from_catalog(q.name)
			self.assertIn(
				"NUEVO CONTENIDO POR REAPLICACIÓN",
				self._rows(q.name)[0]["content"],
				"La reaplicación explícita reemplaza las filas desde los maestros vigentes",
			)
		finally:
			self._set_section(ORIGINAL)

	# ── 6: el contenido de las filas es editable en Draft ───────────────────────

	def test_06_row_content_editable_in_draft(self):
		q = self._make_draft()
		doc = frappe.get_doc("Quotation", q.name)
		doc.proposal_sections[0].content = "<p>EDICIÓN MANUAL DE LA PROPUESTA.</p>"
		doc.save(ignore_permissions=True)
		self.assertIn(
			"EDICIÓN MANUAL",
			self._rows(q.name)[0]["content"],
			"La edición manual de la fila persiste y no se sobrescribe",
		)

	# ── 12: el flujo nuevo NO escribe snapshot narrativo ────────────────────────

	def test_07_no_snapshot_written_in_new_flow(self):
		q = self._make_draft()
		self.assertFalse(
			(self._snap_raw(q.name) or "").strip(), "La generación no escribe proposal_sections_snapshot"
		)
		frappe.get_doc("Quotation", q.name).save(ignore_permissions=True)
		resync_scope_from_catalog(q.name)
		self.assertFalse(
			(self._snap_raw(q.name) or "").strip(),
			"Ni el guardado normal ni el resync escriben proposal_sections_snapshot",
		)

	# ── resync solo en Borrador ─────────────────────────────────────────────────

	def test_08_reapply_blocked_outside_draft(self):
		q = self._make_draft()
		doc = frappe.get_doc("Quotation", q.name)
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		with self.assertRaises(frappe.exceptions.ValidationError):
			resync_scope_from_catalog(q.name)

	# ── secciones opcionales por propuesta ──────────────────────────────────────

	def test_09_optional_excluded_by_default(self):
		q = self._make_draft(select_optional=False)
		refs = [r["proposal_section"] for r in self._rows(q.name)]
		self.assertIn(SECTION, refs, "La fila base (include_by_default=1) siempre entra")
		self.assertNotIn(OPT_SECTION, refs, "La opcional no seleccionada no se materializa")

	def test_10_optional_included_when_selected(self):
		q = self._make_draft(select_optional=True)
		rows = self._rows(q.name)
		refs = [r["proposal_section"] for r in rows]
		self.assertIn(OPT_SECTION, refs, "La opcional seleccionada se materializa")
		opt = next(r for r in rows if r["proposal_section"] == OPT_SECTION)
		self.assertIn(OPT_MARK, opt["content"], "Copia el contenido del maestro opcional")
		self.assertEqual(opt["sequence"], 640, "Conserva la sequence del Template")
		self.assertEqual([r["sequence"] for r in rows], sorted(r["sequence"] for r in rows))
