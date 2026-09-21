# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Rendering del flujo nuevo: los Print Formats leen `Quotation.proposal_sections` (B3).

`get_sections_snapshot` y `_visible_chapter_names`/`section_number` priorizan las filas
materializadas de la Quotation. El `proposal_sections_snapshot` legacy solo se usa cuando NO hay
filas (documentos históricos). El HTML de los Print Formats no cambia. Sin datos de cliente.
"""

import json
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
from erpnext_proposals.erpnext_proposals.utils.printing import (
	get_sections_snapshot,
	section_number,
)

SECTION = "_Test Rnd Section"
TEMPLATE = "_Test Rnd Template"
ITEM = "_Test Rnd Item"
CUSTOMER = "_Test Rnd Customer"
ORIGINAL = "<p>Contenido original de la sección.</p>"


class TestRenderSectionsFromRows(unittest.TestCase):
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
		if not frappe.db.exists("Proposal Section", SECTION):
			frappe.get_doc(
				{
					"doctype": "Proposal Section",
					"section_name": SECTION,
					"title": "Sección Render",
					"content": ORIGINAL,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			t = frappe.get_doc({"doctype": "Proposal Template", "template_name": TEMPLATE})
			t.append("sections", {"proposal_section": SECTION, "sequence": 10, "include_by_default": 1})
			t.insert(ignore_permissions=True)
		cls.cost_center = get_test_cost_center(cls.company)
		cls._quotations = []

	@classmethod
	def tearDownClass(cls):
		for n in cls._quotations:
			if frappe.db.exists("Quotation", n):
				try:
					frappe.delete_doc("Quotation", n, force=True, ignore_permissions=True)
				except Exception:
					pass
		cleanup_test_phases(getattr(cls, "_phases", None))
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		super().tearDownClass()

	def _make_draft(self):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": CUSTOMER,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": f"RND-{frappe.generate_hash(length=8)}",
				"proposal_template": TEMPLATE,
				"proposal_title": "Render",
				"proposal_cost_center": self.cost_center,
				"selling_price_list": get_test_price_list(),
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self._quotations.append(doc.name)
		return frappe.get_doc("Quotation", doc.name)

	# ── el render lee las filas materializadas ──────────────────────────────────

	def test_01_get_sections_snapshot_reads_rows(self):
		doc = self._make_draft()
		res = get_sections_snapshot(doc)
		self.assertTrue(res["valid"], "Con filas materializadas el resultado es válido")
		self.assertEqual(res["reason"], "ok")
		self.assertEqual(len(res["sections"]), 1)
		s = res["sections"][0]
		self.assertEqual(s["source_section"], SECTION, "source_section == Proposal Section origen")
		self.assertIn("Contenido original", s["content"])
		self.assertEqual(s["sequence"], 10)

	def test_02_section_number_from_rows(self):
		doc = self._make_draft()
		self.assertEqual(
			section_number(doc, SECTION), "1", "La numeración de capítulos se deriva de las filas"
		)

	def test_03_hidden_title_excluded_from_numbering(self):
		doc = self._make_draft()
		doc.proposal_sections[0].hide_title = 1
		doc.save(ignore_permissions=True)
		doc = frappe.get_doc("Quotation", doc.name)
		self.assertEqual(
			section_number(doc, SECTION), "", "Una sección con hide_title=1 queda fuera del 1..N"
		)

	# ── prioridad filas > snapshot legacy ───────────────────────────────────────

	def test_04_rows_win_over_snapshot(self):
		doc = self._make_draft()
		# Inyecta un snapshot legacy con contenido distinto: las filas deben ganar.
		doc.proposal_sections_snapshot = json.dumps(
			[
				{
					"sequence": 10,
					"title": "Título legacy",
					"content": "<p>CONTENIDO LEGACY QUE NO DEBE APARECER.</p>",
					"source_section": SECTION,
					"is_executive_summary": 0,
					"captured_on": "2020-01-01T00:00:00",
				}
			],
			ensure_ascii=False,
		)
		res = get_sections_snapshot(doc)
		self.assertIn("Contenido original", res["sections"][0]["content"])
		self.assertNotIn("LEGACY", res["sections"][0]["content"])

	# ── fallback histórico: sin filas, se lee el snapshot ───────────────────────

	def test_05_legacy_snapshot_read_when_no_rows(self):
		legacy = frappe._dict(
			{
				"proposal_sections_snapshot": json.dumps(
					[
						{
							"sequence": 10,
							"title": "Título histórico",
							"content": "<p>Contenido histórico.</p>",
							"source_section": SECTION,
							"is_executive_summary": 0,
							"captured_on": "2020-01-01T00:00:00",
						}
					],
					ensure_ascii=False,
				)
			}
		)
		res = get_sections_snapshot(legacy)
		self.assertTrue(res["valid"], "Un documento histórico sin filas lee el snapshot legacy")
		self.assertIn("Contenido histórico", res["sections"][0]["content"])
