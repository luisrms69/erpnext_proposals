# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""UX "Contenido de propuesta": edición cómoda + orden nativo de `Quotation.proposal_sections`.

Cubre el comportamiento NUEVO de esta línea de trabajo:
- materialización aplica el Template a las filas;
- reordenar (idx) sincroniza `sequence` en Borrador (`_sync_proposal_section_sequence`), que sigue siendo
  el orden canónico que consumen el Print Format y `get_sections_snapshot`;
- agregar/eliminar/editar filas en Borrador;
- una sección ad-hoc con `proposal_section` vacío es válida (sin excepciones artificiales).

La inmutabilidad en submitted la cubre `test_freeze_sections_docstatus`. La vista previa es render de
cliente (JS) y se valida manualmente. Sin datos de cliente ni contenido del catálogo privado.
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
from erpnext_proposals.erpnext_proposals.utils.printing import get_sections_snapshot

SECTIONS = [
	("_Test UX Sec A", "<p>Contenido A.</p>"),
	("_Test UX Sec B", "<p>Contenido B.</p>"),
	("_Test UX Sec C", "<p>Contenido C.</p>"),
]
TEMPLATE = "_Test UX Template"
ITEM = "_Test UX Item"
CUSTOMER = "_Test UX Customer"


class TestProposalContentUX(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		cls._fy = ensure_current_fiscal_year()
		cls.cost_center = get_test_cost_center(cls.company)
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
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": ITEM,
					"item_group": get_test_item_group(),
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
		for name, content in SECTIONS:
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
			for i, (name, _c) in enumerate(SECTIONS, start=1):
				t.append("sections", {"proposal_section": name, "sequence": i * 10, "include_by_default": 1})
			t.insert(ignore_permissions=True)
		cls._quotations = []
		frappe.db.commit()  # nosemgrep — fixtures de test

	@classmethod
	def tearDownClass(cls):
		for n in cls._quotations:
			if frappe.db.exists("Quotation", n):
				try:
					frappe.delete_doc("Quotation", n, force=True, ignore_permissions=True)
				except Exception:
					pass
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		frappe.db.commit()  # nosemgrep — limpieza de test
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
				"proposal_group": f"UX-{frappe.generate_hash(length=8)}",
				"proposal_template": TEMPLATE,
				"proposal_title": "UX",
				"proposal_cost_center": self.cost_center,
				"selling_price_list": get_test_price_list(),
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self._quotations.append(doc.name)
		return doc

	def _ordered_titles(self, name):
		doc = frappe.get_doc("Quotation", name)
		return [r.title for r in sorted(doc.proposal_sections, key=lambda r: r.sequence or 0)]

	# 1) materializar aplica el Template (3 filas, orden del Template)
	def test_1_materialize_applies_template(self):
		q = self._make_draft()
		self.assertEqual(self._ordered_titles(q.name), [f"Título {n}" for n, _ in SECTIONS])

	# 2) reordenar (idx) → sequence sigue el nuevo orden; readers/PF reflejan
	def test_2_reorder_syncs_sequence_and_readers(self):
		q = self._make_draft()
		doc = frappe.get_doc("Quotation", q.name)
		rows = sorted(doc.proposal_sections, key=lambda r: r.sequence or 0)
		# reconstruir en orden INVERSO (simula un arrastre: las filas CONSERVAN su `sequence`, solo cambia
		# el orden visual/idx) → el sync detecta que idx≠sequence y renumera 1..N según el nuevo orden.
		data = [
			{
				"title": r.title,
				"content": r.content,
				"hide_title": r.hide_title,
				"proposal_section": r.proposal_section,
				"is_executive_summary": r.is_executive_summary,
				"sequence": r.sequence,
			}
			for r in reversed(rows)
		]
		doc.set("proposal_sections", data)
		doc.save(ignore_permissions=True)

		expected = [f"Título {n}" for n, _ in SECTIONS][::-1]
		self.assertEqual(self._ordered_titles(q.name), expected, "readers ordenan por sequence sincronizado")
		# sequence contiguo 1..N en el nuevo orden
		fresh = frappe.get_doc("Quotation", q.name)
		self.assertEqual(sorted(r.sequence for r in fresh.proposal_sections), [1, 2, 3])
		# el lector que usa el Print Format refleja el mismo orden y contenido
		snap = get_sections_snapshot(fresh)
		snap_titles = [s["title"] for s in snap.get("sections", [])]
		self.assertEqual(snap_titles, expected, "get_sections_snapshot (fuente del PF) sigue el orden")

	# 3) agregar sección ad-hoc con proposal_section vacío (válido, sin excepción artificial)
	def test_3_add_manual_section_empty_link(self):
		q = self._make_draft()
		doc = frappe.get_doc("Quotation", q.name)
		doc.append(
			"proposal_sections",
			{"title": "Sección manual", "content": "<p>Ad-hoc.</p>", "hide_title": 0},
		)
		doc.save(ignore_permissions=True)
		fresh = frappe.get_doc("Quotation", q.name)
		self.assertEqual(len(fresh.proposal_sections), len(SECTIONS) + 1)
		manual = next(r for r in fresh.proposal_sections if r.title == "Sección manual")
		self.assertFalse(manual.proposal_section, "sección ad-hoc: proposal_section vacío")
		self.assertTrue(int(manual.sequence) > 0, "sequence asignado por el sync")
		# sequence contiguo 1..N+1
		self.assertEqual(
			sorted(r.sequence for r in fresh.proposal_sections), list(range(1, len(SECTIONS) + 2))
		)

	# 4) eliminar fila → persiste, orden preservado y `sequence` sigue estrictamente creciente
	#    (borrar la del medio deja gaps válidos [10,30]; el sync NO renumera gratuitamente).
	def test_4_delete_row(self):
		q = self._make_draft()
		doc = frappe.get_doc("Quotation", q.name)
		doc.proposal_sections.pop(1)  # quita la del medio
		doc.save(ignore_permissions=True)
		fresh = frappe.get_doc("Quotation", q.name)
		self.assertEqual(len(fresh.proposal_sections), len(SECTIONS) - 1)
		self.assertEqual(
			self._ordered_titles(q.name), [f"Título {SECTIONS[0][0]}", f"Título {SECTIONS[2][0]}"]
		)
		seqs = [r.sequence for r in sorted(fresh.proposal_sections, key=lambda r: r.sequence or 0)]
		self.assertEqual(seqs, sorted(set(seqs)), "sequence estrictamente creciente (gaps válidos)")

	# 5) editar title/content/hide_title persiste
	def test_5_edit_fields_persist(self):
		q = self._make_draft()
		doc = frappe.get_doc("Quotation", q.name)
		row = sorted(doc.proposal_sections, key=lambda r: r.sequence or 0)[0]
		row.title = "Título editado"
		row.content = "<p>Contenido editado.</p>"
		row.hide_title = 1
		doc.save(ignore_permissions=True)
		fresh = frappe.get_doc("Quotation", q.name)
		edited = sorted(fresh.proposal_sections, key=lambda r: r.sequence or 0)[0]
		self.assertEqual(edited.title, "Título editado")
		self.assertIn("Contenido editado", edited.content)
		self.assertEqual(int(edited.hide_title), 1)

	# 6) sequence NO se toca en submitted (guard docstatus del sync)
	def test_6_sync_skips_when_not_draft(self):
		from erpnext_proposals.erpnext_proposals.utils.quotation import _sync_proposal_section_sequence

		doc = frappe.get_doc("Quotation", self._make_draft().name)
		doc.docstatus = 1  # simular submitted en memoria
		for r in doc.proposal_sections:
			r.sequence = 99  # valor "sucio"
		_sync_proposal_section_sequence(doc)
		self.assertTrue(
			all(r.sequence == 99 for r in doc.proposal_sections), "no toca filas si no es Borrador"
		)
