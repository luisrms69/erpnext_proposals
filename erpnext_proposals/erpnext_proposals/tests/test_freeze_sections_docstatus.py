# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Freeze narrativo simplificado: docstatus es el congelamiento (B6).

`freeze_proposal` ya no genera ni sincroniza `proposal_sections_snapshot`. Las filas
`proposal_sections` materializadas en Borrador quedan inmutables por `docstatus` al pasar a
En Revisión/Submit; el PDF oficial es la evidencia histórica. El render lee las filas. Sin datos
de cliente.
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
from erpnext_proposals.erpnext_proposals.utils.printing import get_sections_snapshot

SECTION = "_Test Frz Section"
TEMPLATE = "_Test Frz Template"
ITEM = "_Test Frz Item"
CUSTOMER = "_Test Frz Customer"
ORIGINAL = "<p>Contenido original de la sección.</p>"

_IMMUTABLE_EXCEPTIONS = (
	frappe.exceptions.ValidationError,
	frappe.exceptions.UpdateAfterSubmitError,
)


class TestFreezeSectionsDocstatus(unittest.TestCase):
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
					"title": "Sección Freeze",
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
				"proposal_group": f"FRZ-{frappe.generate_hash(length=8)}",
				"proposal_template": TEMPLATE,
				"proposal_title": "Freeze",
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
		doc.reload()
		return doc

	# ── 12: submit no escribe snapshot narrativo ────────────────────────────────

	def test_01_submit_writes_no_narrative_snapshot(self):
		doc = self._make_submitted()
		self.assertEqual(doc.docstatus, 1)
		self.assertTrue(doc.proposal_sections, "Las filas materializadas persisten tras el submit")
		self.assertFalse(
			(doc.get("proposal_sections_snapshot") or "").strip(),
			"El freeze/submit no escribe proposal_sections_snapshot",
		)

	# ── 7: las filas quedan inmutables por docstatus ────────────────────────────

	def test_02_submitted_rows_immutable(self):
		doc = self._make_submitted()
		fresh = frappe.get_doc("Quotation", doc.name)
		fresh.proposal_sections[0].content = "<p>INTENTO DE EDICIÓN POST-SUBMIT.</p>"
		with self.assertRaises(_IMMUTABLE_EXCEPTIONS):
			fresh.save()
		reloaded = frappe.get_doc("Quotation", doc.name)
		self.assertIn(
			"Contenido original", reloaded.proposal_sections[0].content, "La fila permanece intacta"
		)

	# ── 8: cambiar el maestro tras submit no altera las filas ───────────────────

	def test_03_master_change_after_submit_not_reflected(self):
		doc = self._make_submitted()
		frappe.db.set_value(
			"Proposal Section", SECTION, "content", "<p>CAMBIO POST-SUBMIT.</p>", update_modified=False
		)
		try:
			reloaded = frappe.get_doc("Quotation", doc.name)
			self.assertIn(
				"Contenido original",
				reloaded.proposal_sections[0].content,
				"Las filas congeladas no releen el maestro tras el submit",
			)
		finally:
			frappe.db.set_value("Proposal Section", SECTION, "content", ORIGINAL, update_modified=False)

	# ── 8: el render del submitted usa las filas ────────────────────────────────

	def test_04_render_uses_rows_after_submit(self):
		doc = self._make_submitted()
		res = get_sections_snapshot(doc)
		self.assertTrue(res["valid"], "El render del submitted lee las filas materializadas")
		self.assertIn("Contenido original", res["sections"][0]["content"])
		self.assertEqual(res["sections"][0]["source_section"], SECTION)
