# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""UX "Contenido de propuesta" — orden de `Quotation.proposal_sections` por drag libre (punto medio).

`sequence` es dato SEMÁNTICO (posición real del documento), oculto al usuario, NO espejo de `idx`. El
bloque sintético de Items/Inversión del Print Format se ancla en `sequence == 500` (`<500` antes, `>=500`
después). El drag es LIBRE y puede cruzar esa frontera: al soltar, cada fila movida (o ad-hoc) recibe un
valor ENTRE sus vecinos reales; una fila que ya respeta el orden se conserva. Nunca `sequence = idx`,
nunca 0/vacío.

Fix de ORDEN/reorder. El read-only de preview/PDF (Fix 2) vive en `test_preview_pdf_readonly.py`. Sin
datos de cliente ni contenido del catálogo privado.
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

# (section_name, título, content, sequence)  — 2 antes del 500, 2 después. Nombres nuevos (`UXB`) para
# no colisionar con fixtures previos ya persistidos en el site de tests.
SECTIONS = [
	("_Test UXB Sec A", "UX-A", "<p>A</p>", 10),
	("_Test UXB Sec B", "UX-B", "<p>B</p>", 20),
	("_Test UXB Sec C", "UX-C", "<p>C</p>", 610),
	("_Test UXB Sec D", "UX-D", "<p>D</p>", 620),
]
TEMPLATE = "_Test UXB Template"
ITEM = "_Test UXB Item"
CUSTOMER = "_Test UXB Customer"
B = 500  # landmark del bloque de Items


def _fixtures(cls):
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
	for name, title, content, _seq in SECTIONS:
		if not frappe.db.exists("Proposal Section", name):
			frappe.get_doc(
				{
					"doctype": "Proposal Section",
					"section_name": name,
					"title": title,
					"content": content,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
	if not frappe.db.exists("Proposal Template", TEMPLATE):
		t = frappe.get_doc({"doctype": "Proposal Template", "template_name": TEMPLATE})
		for name, _title, _content, seq in SECTIONS:
			t.append("sections", {"proposal_section": name, "sequence": seq, "include_by_default": 1})
		t.insert(ignore_permissions=True)
	cls._quotations = []
	frappe.db.commit()  # nosemgrep — fixtures de test


def _make_draft(cls):
	doc = frappe.get_doc(
		{
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": CUSTOMER,
			"company": cls.company,
			"currency": "MXN",
			"transaction_date": frappe.utils.today(),
			"proposal_group": f"UX-{frappe.generate_hash(length=8)}",
			"proposal_template": TEMPLATE,
			"proposal_title": "UX",
			"proposal_cost_center": cls.cost_center,
			"selling_price_list": get_test_price_list(),
			"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}],
		}
	)
	doc.insert(ignore_permissions=True, ignore_mandatory=True)
	cls._quotations.append(doc.name)
	return doc


class TestProposalSectionOrder(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_fixtures(cls)

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

	def _seqs(self, name):
		doc = frappe.get_doc("Quotation", name)
		return {r.title: int(r.sequence) for r in doc.proposal_sections}

	def _order(self, name):
		doc = frappe.get_doc("Quotation", name)
		return [r.title for r in sorted(doc.proposal_sections, key=lambda r: int(r.sequence or 0))]

	def _rebuild(self, name, titles, extra=None):
		"""Reordena `proposal_sections` en el orden `titles` (simula un arrastre libre: cambia el orden/idx,
		conserva la `sequence` de cada fila existente). `extra` = {título: dict} de filas ad-hoc SIN
		`sequence`, ubicadas por su título en `titles`."""
		doc = frappe.get_doc("Quotation", name)
		by = {r.title: r for r in doc.proposal_sections}
		data = []
		for t in titles:
			if t in by:
				r = by[t]
				data.append(
					{
						"title": r.title,
						"content": r.content,
						"hide_title": r.hide_title,
						"proposal_section": r.proposal_section,
						"sequence": r.sequence,
					}
				)
			elif extra and t in extra:
				data.append(extra[t])
		doc.set("proposal_sections", data)
		doc.save(ignore_permissions=True)
		return doc

	# 1) materializar preserva las sequences del Template (NO renumera 1..N)
	def test_1_materialize_preserves_template_sequences(self):
		q = _make_draft(self)
		self.assertEqual(self._seqs(q.name), {"UX-A": 10, "UX-B": 20, "UX-C": 610, "UX-D": 620})

	# 2) guardar sin reordenar es no-op (idempotente): las sequences no cambian
	def test_2_save_without_reorder_is_noop(self):
		q = _make_draft(self)
		frappe.get_doc("Quotation", q.name).save(ignore_permissions=True)
		self.assertEqual(self._seqs(q.name), {"UX-A": 10, "UX-B": 20, "UX-C": 610, "UX-D": 620})

	# 3) reorden SIN cruzar: mover B antes de A → punto medio, ambas siguen <500, orden [B,A,C,D]
	def test_3_reorder_no_cross(self):
		q = _make_draft(self)
		self._rebuild(q.name, ["UX-B", "UX-A", "UX-C", "UX-D"])
		s = self._seqs(q.name)
		self.assertLess(s["UX-B"], s["UX-A"])
		self.assertLess(s["UX-A"], B)
		self.assertLess(s["UX-B"], B)
		self.assertEqual(self._order(q.name), ["UX-B", "UX-A", "UX-C", "UX-D"])

	# 4) drag que CRUZA hacia abajo: D (>=500) arrastrada entre A(10) y B(20) → punto medio 15 (<500)
	def test_4_drag_crosses_boundary_down(self):
		q = _make_draft(self)
		self._rebuild(q.name, ["UX-A", "UX-D", "UX-B", "UX-C"])
		s = self._seqs(q.name)
		self.assertLess(s["UX-D"], B, "D cruzó a ANTES del bloque de Items")
		self.assertEqual(s["UX-D"], (10 + 20) // 2, "valor intermedio entre sus vecinos reales (15)")
		self.assertEqual(self._order(q.name), ["UX-A", "UX-D", "UX-B", "UX-C"])

	# 5) drag que CRUZA hacia arriba: A (<500) arrastrada entre C(610) y D(620) → punto medio 615 (>=500)
	def test_5_drag_crosses_boundary_up(self):
		q = _make_draft(self)
		self._rebuild(q.name, ["UX-B", "UX-C", "UX-A", "UX-D"])
		s = self._seqs(q.name)
		self.assertGreaterEqual(s["UX-A"], B, "A cruzó a DESPUÉS del bloque de Items")
		self.assertEqual(s["UX-A"], (610 + 620) // 2, "valor intermedio entre C y D (615)")
		self.assertEqual(self._order(q.name), ["UX-B", "UX-C", "UX-A", "UX-D"])

	# 6) sección ad-hoc ENTRE dos secciones → valor intermedio EN RANGO (>0), posicionada entre vecinos
	def test_6_adhoc_between_neighbors(self):
		q = _make_draft(self)
		self._rebuild(
			q.name,
			["UX-A", "UX-B", "UX-C", "UX-ADHOC", "UX-D"],
			extra={"UX-ADHOC": {"title": "UX-ADHOC", "content": "<p>adhoc</p>", "hide_title": 0}},
		)
		s = self._seqs(q.name)
		self.assertGreater(s["UX-ADHOC"], 0, "nunca 0/vacío")
		self.assertTrue(s["UX-C"] < s["UX-ADHOC"] < s["UX-D"], "queda estrictamente entre sus vecinos")
		self.assertEqual(self._order(q.name), ["UX-A", "UX-B", "UX-C", "UX-ADHOC", "UX-D"])

	# 7) sección ad-hoc AL FRENTE → valor > 0, primera en el orden
	def test_7_adhoc_at_front(self):
		q = _make_draft(self)
		self._rebuild(
			q.name,
			["UX-ADHOC", "UX-A", "UX-B", "UX-C", "UX-D"],
			extra={"UX-ADHOC": {"title": "UX-ADHOC", "content": "<p>adhoc</p>", "hide_title": 0}},
		)
		s = self._seqs(q.name)
		self.assertGreater(s["UX-ADHOC"], 0)
		self.assertEqual(self._order(q.name)[0], "UX-ADHOC")

	# 8) eliminar una fila conserva el orden y los readers lo reflejan
	def test_8_delete_preserves_order(self):
		q = _make_draft(self)
		doc = frappe.get_doc("Quotation", q.name)
		doc.proposal_sections = [r for r in doc.proposal_sections if r.title != "UX-B"]
		doc.save(ignore_permissions=True)
		self.assertEqual(self._order(q.name), ["UX-A", "UX-C", "UX-D"])
		snap = get_sections_snapshot(frappe.get_doc("Quotation", q.name))
		self.assertEqual([e["title"] for e in snap["sections"]], ["UX-A", "UX-C", "UX-D"])
