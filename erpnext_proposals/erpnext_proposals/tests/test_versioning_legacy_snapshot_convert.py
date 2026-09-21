# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Compatibilidad puntual de entrada: legacy snapshot → filas al versionar (B5).

Una propuesta Rechazada histórica que solo tiene `proposal_sections_snapshot` (sin filas
materializadas) se convierte UNA SOLA VEZ a filas `proposal_sections` en la nueva versión. El
documento histórico no se modifica. Si la fuente moderna ya tiene filas, el snapshot se ignora
(las filas ganan). Sin datos de cliente.
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
from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import create_new_proposal_version

SECTION = "_Test Leg Section"
TEMPLATE = "_Test Leg Template"
ITEM = "_Test Leg Item"
CUSTOMER = "_Test Leg Customer"
ORIGINAL = "<p>Contenido original de la sección.</p>"
LEGACY_CONTENT = "<p>CONTENIDO CONGELADO EN EL SNAPSHOT LEGACY.</p>"


def _snap_entry(source, content, seq=10, hide=0, exec_sum=0, title="Título legacy"):
	return {
		"sequence": seq,
		"title": title,
		"content": content,
		"source_section": source,
		"is_executive_summary": exec_sum,
		"hide_title": hide,
		"captured_on": "2020-01-01T00:00:00",
	}


class TestVersioningLegacySnapshotConvert(unittest.TestCase):
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
					"title": "Sección Legacy",
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
				"proposal_group": f"LEG-{frappe.generate_hash(length=8)}",
				"proposal_template": TEMPLATE,
				"proposal_title": "Legacy",
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

	def _make_legacy(self, entries):
		"""Simula una Rechazada histórica: sin filas materializadas, solo snapshot congelado."""
		name = self._make_submitted()
		frappe.db.delete(
			"Proposal Quotation Section",
			{"parent": name, "parenttype": "Quotation", "parentfield": "proposal_sections"},
		)
		frappe.db.set_value(
			"Quotation", name, "proposal_sections_snapshot", json.dumps(entries), update_modified=False
		)
		return name

	def _rows(self, name):
		doc = frappe.get_doc("Quotation", name)
		return sorted(
			[r.as_dict() for r in (doc.proposal_sections or [])],
			key=lambda r: r.get("sequence") or 0,
		)

	# ── 10: conversión snapshot→filas una sola vez ──────────────────────────────

	def test_01_legacy_snapshot_converted_to_rows(self):
		old = self._make_legacy([_snap_entry(SECTION, LEGACY_CONTENT, seq=10)])
		self.assertEqual(self._rows(old), [], "El origen legacy no tiene filas materializadas")
		v2 = create_new_proposal_version(old, reason="convertir legacy")
		self._quotations.append(v2)
		rows = self._rows(v2)
		self.assertEqual(len(rows), 1, "El snapshot legacy se convierte a una fila")
		self.assertEqual(rows[0]["proposal_section"], SECTION)
		self.assertIn("SNAPSHOT LEGACY", rows[0]["content"], "Conserva el contenido congelado")
		self.assertEqual(rows[0]["sequence"], 10)

	def test_02_converted_version_has_no_snapshot(self):
		old = self._make_legacy([_snap_entry(SECTION, LEGACY_CONTENT)])
		v2 = create_new_proposal_version(old, reason="sin snapshot")
		self._quotations.append(v2)
		raw = frappe.db.get_value("Quotation", v2, "proposal_sections_snapshot")
		self.assertFalse((raw or "").strip(), "La versión convertida no arrastra snapshot")

	# ── 11: el histórico no se modifica ─────────────────────────────────────────

	def test_03_historical_source_untouched(self):
		old = self._make_legacy([_snap_entry(SECTION, LEGACY_CONTENT)])
		create_new_proposal_version(old, reason="no tocar histórico")
		# el histórico conserva su snapshot y sigue sin filas
		self.assertEqual(self._rows(old), [], "El histórico no gana filas")
		raw = frappe.db.get_value("Quotation", old, "proposal_sections_snapshot")
		self.assertIn("SNAPSHOT LEGACY", raw or "", "El snapshot histórico permanece intacto")

	# ── conversión robusta ante Proposal Section inexistente ────────────────────

	def test_04_dangling_section_preserved_as_manual_row(self):
		old = self._make_legacy([_snap_entry("_Nonexistent Section XYZ", LEGACY_CONTENT)])
		v2 = create_new_proposal_version(old, reason="link colgante")
		self._quotations.append(v2)
		rows = self._rows(v2)
		self.assertEqual(len(rows), 1, "La conversión no se rompe por un Link colgante")
		self.assertFalse(rows[0].get("proposal_section"), "Section inexistente → fila manual sin Link")
		self.assertIn("SNAPSHOT LEGACY", rows[0]["content"], "El contenido se conserva")

	# ── fuente moderna: las filas ganan, el snapshot se ignora ──────────────────

	def test_05_modern_rows_win_over_snapshot(self):
		name = self._make_submitted()  # moderno: tiene filas materializadas
		# ruido: un snapshot legacy con contenido distinto NO debe usarse
		frappe.db.set_value(
			"Quotation",
			name,
			"proposal_sections_snapshot",
			json.dumps([_snap_entry(SECTION, "<p>NO USAR ESTE SNAPSHOT.</p>")]),
			update_modified=False,
		)
		v2 = create_new_proposal_version(name, reason="filas ganan")
		self._quotations.append(v2)
		rows = self._rows(v2)
		self.assertEqual(len(rows), 1)
		self.assertIn("Contenido original", rows[0]["content"], "Copia las filas, no el snapshot")
		self.assertNotIn("NO USAR", rows[0]["content"])
