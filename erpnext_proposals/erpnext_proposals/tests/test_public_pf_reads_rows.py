# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""El Print Format PÚBLICO `Propuesta Comercial` lee las filas materializadas (B10 / ADR-0022).

Regresión del hallazgo: el PF público reconstruía la narrativa desde `Proposal Template.sections` en
vivo cuando no había snapshot. Ahora usa exclusivamente `get_sections_snapshot(doc)` (filas
materializadas para el flujo nuevo; snapshot legacy solo para históricos). Un documento formal nuevo
NUNCA relee Proposal Template / Proposal Section. Sin datos de cliente.
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

SECTION = "_Test PubPF Section"
TEMPLATE = "_Test PubPF Template"
ITEM = "_Test PubPF Item"
CUSTOMER = "_Test PubPF Customer"
MATERIALIZED = "CONTENIDO MATERIALIZADO UNICO B10"
ORIGINAL = f"<p>{MATERIALIZED}.</p>"


class TestPublicPFReadsRows(unittest.TestCase):
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
					"title": "Seccion PubPF",
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

	def _make_submitted(self):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": CUSTOMER,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": f"PUBPF-{frappe.generate_hash(length=8)}",
				"proposal_template": TEMPLATE,
				"proposal_title": "PubPF",
				"proposal_cost_center": self.cost_center,
				"selling_price_list": get_test_price_list(),
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self._quotations.append(doc.name)
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		return doc.name

	def _render(self, name):
		return frappe.get_print("Quotation", name, print_format="Propuesta Comercial")

	# ── el PF renderiza la narrativa desde las filas materializadas ─────────────

	def test_01_public_pf_renders_from_materialized_rows(self):
		name = self._make_submitted()
		# nuevo flujo: no hay snapshot; la narrativa vive en proposal_sections (rows)
		self.assertFalse(
			(frappe.db.get_value("Quotation", name, "proposal_sections_snapshot") or "").strip(),
			"precondición: propuesta nueva sin snapshot",
		)
		self.assertTrue(frappe.get_doc("Quotation", name).proposal_sections, "precondición: filas presentes")
		html = self._render(name)
		self.assertIn(MATERIALIZED, html, "el PF público renderiza el contenido materializado de las filas")

	# ── regresión: cambiar el master tras submit NO cambia el render (no relee vivo) ──

	def test_02_master_change_after_submit_not_reflected_in_pf(self):
		name = self._make_submitted()
		frappe.db.set_value(
			"Proposal Section",
			SECTION,
			"content",
			"<p>CONTENIDO VIVO QUE NO DEBE APARECER.</p>",
			update_modified=False,
		)
		frappe.clear_document_cache("Proposal Section", SECTION)
		try:
			html = self._render(name)
			self.assertIn(MATERIALIZED, html, "sigue mostrando el contenido materializado")
			self.assertNotIn(
				"CONTENIDO VIVO QUE NO DEBE APARECER",
				html,
				"el PF NO relee Proposal Section en vivo para un documento formal",
			)
		finally:
			frappe.db.set_value("Proposal Section", SECTION, "content", ORIGINAL, update_modified=False)
			frappe.clear_document_cache("Proposal Section", SECTION)
