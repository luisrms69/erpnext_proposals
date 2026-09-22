# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Versionado del flujo nuevo: copia de `proposal_sections` como datos normales (B4).

`create_new_proposal_version` hereda las filas materializadas de la propuesta anterior como una child
table normal (copia literal, independiente de los maestros) y NO genera/copia
`proposal_sections_snapshot`. La nueva versión queda editable en Borrador. Sin datos de cliente.
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
from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import create_new_proposal_version

SECTION = "_Test Ver Section"
TEMPLATE = "_Test Ver Template"
ITEM = "_Test Ver Item"
CUSTOMER = "_Test Ver Customer"
ORIGINAL = "<p>Contenido original de la sección.</p>"


class TestVersioningSectionsRows(unittest.TestCase):
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
					"title": "Sección Versión",
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

	def _make_rechazada(self):
		"""Crea una propuesta moderna (con filas materializadas), la submitea y la marca Rechazada."""
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": CUSTOMER,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": f"VER-{frappe.generate_hash(length=8)}",
				"proposal_template": TEMPLATE,
				"proposal_title": "Versión",
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
		frappe.db.set_value("Quotation", doc.name, "workflow_state", "Rechazada", update_modified=False)
		return doc.name

	def _rows(self, name):
		doc = frappe.get_doc("Quotation", name)
		return sorted(
			[r.as_dict() for r in (doc.proposal_sections or [])],
			key=lambda r: r.get("sequence") or 0,
		)

	# ── la nueva versión copia las filas literalmente ───────────────────────────

	def test_01_new_version_copies_rows_literally(self):
		old = self._make_rechazada()
		self.assertEqual(len(self._rows(old)), 1, "El origen moderno tiene filas materializadas")
		# cambiar el maestro DESPUÉS de versionar no debe afectar la copia literal
		frappe.db.set_value(
			"Proposal Section", SECTION, "content", "<p>CAMBIO MAESTRO.</p>", update_modified=False
		)
		try:
			v2 = create_new_proposal_version(old, reason="copia de filas")
			self._quotations.append(v2)
			rows = self._rows(v2)
			self.assertEqual(len(rows), 1, "La versión copia la fila")
			self.assertEqual(rows[0]["proposal_section"], SECTION)
			self.assertIn("Contenido original", rows[0]["content"], "Copia LITERAL, no relee el maestro")
			self.assertEqual(rows[0]["sequence"], 10)
		finally:
			frappe.db.set_value("Proposal Section", SECTION, "content", ORIGINAL, update_modified=False)

	def test_02_new_version_writes_no_snapshot(self):
		old = self._make_rechazada()
		v2 = create_new_proposal_version(old, reason="sin snapshot")
		self._quotations.append(v2)
		raw = frappe.db.get_value("Quotation", v2, "proposal_sections_snapshot")
		self.assertFalse((raw or "").strip(), "La versión nueva no genera proposal_sections_snapshot")

	def test_03_new_version_is_editable_draft(self):
		old = self._make_rechazada()
		v2 = create_new_proposal_version(old, reason="editable")
		self._quotations.append(v2)
		doc = frappe.get_doc("Quotation", v2)
		self.assertEqual(doc.docstatus, 0, "La versión nueva es Borrador")
		self.assertEqual(doc.workflow_state, "Borrador")
		doc.proposal_sections[0].content = "<p>EDICIÓN EN LA NUEVA VERSIÓN.</p>"
		doc.save(ignore_permissions=True)
		self.assertIn("EDICIÓN EN LA NUEVA VERSIÓN", self._rows(v2)[0]["content"])
