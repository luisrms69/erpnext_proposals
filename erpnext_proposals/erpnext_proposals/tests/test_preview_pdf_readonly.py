# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Fix 2: la Vista previa / generación comercial es de LECTURA — NUNCA muta la narrativa materializada.

Regresión del bug de QA: la acción de preview/PDF disparaba un resync que reconstruía
`Quotation.proposal_sections` desde el Template, descartando las ediciones manuales. Aquí se verifica:
- `resync_scope_from_catalog` (acción explícita de scope/costos) YA NO toca `proposal_sections`;
- el lector que consume el Print Format (`get_sections_snapshot`) refleja los valores editados y NO muta
  las filas.

La eliminación del resync del botón de preview/PDF vive en `quotation.js` (cliente) y se valida en el QA
manual. Sin datos de cliente ni contenido del catálogo privado.
"""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import cleanup_fiscal_year
from erpnext_proposals.erpnext_proposals.tests.test_proposal_content_ux import _fixtures, _make_draft
from erpnext_proposals.erpnext_proposals.utils.printing import get_sections_snapshot
from erpnext_proposals.erpnext_proposals.utils.quotation import resync_scope_from_catalog

QA_MARK = "QA-EDIT-XYZ"


class TestPreviewPdfReadOnly(unittest.TestCase):
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

	def _edit_and_save(self, name):
		"""Edita title/content/hide_title, reordena (D antes de B), agrega ad-hoc y elimina UX-C; guarda."""
		doc = frappe.get_doc("Quotation", name)
		by = {r.title: r for r in doc.proposal_sections}
		by["UX-A"].title = "UX-A editado"
		by["UX-A"].content = f"<p>{QA_MARK}</p>"
		by["UX-A"].hide_title = 1

		def _d(r):
			return {
				"title": r.title,
				"content": r.content,
				"hide_title": r.hide_title,
				"proposal_section": r.proposal_section,
				"sequence": r.sequence,
			}

		data = [_d(by["UX-A"]), _d(by["UX-D"]), _d(by["UX-B"])]  # UX-C eliminada, D antes de B
		data.append({"title": "UX-ADHOC", "content": "<p>adhoc QA</p>", "hide_title": 0})
		doc.set("proposal_sections", data)
		if not doc.get("workflow_state"):
			doc.workflow_state = "Borrador"
		doc.save(ignore_permissions=True)
		return frappe.get_doc("Quotation", name)

	def _snapshot(self, name):
		doc = frappe.get_doc("Quotation", name)
		return [
			(r.title, r.content, int(r.hide_title or 0), int(r.sequence or 0))
			for r in sorted(doc.proposal_sections, key=lambda r: int(r.sequence or 0))
		]

	# 1) resync explícito NO reconstruye la narrativa: proposal_sections idéntica antes/después
	def test_1_resync_does_not_touch_narrative(self):
		q = _make_draft(self)
		self._edit_and_save(q.name)
		before = self._snapshot(q.name)
		frappe.db.set_value("Quotation", q.name, "workflow_state", "Borrador")  # gate del resync
		resync_scope_from_catalog(q.name)
		after = self._snapshot(q.name)
		self.assertEqual(before, after, "el resync de scope/costos NO debe mutar proposal_sections")
		self.assertTrue(any(QA_MARK in c for _t, c, _h, _s in after), "la edición sobrevive al resync")
		self.assertTrue(any(t == "UX-A editado" for t, _c, _h, _s in after))

	# 2) el lector del Print Format refleja los valores editados y NO muta las filas
	def test_2_reader_reflects_edits_and_is_read_only(self):
		q = _make_draft(self)
		self._edit_and_save(q.name)
		before = self._snapshot(q.name)
		snap = get_sections_snapshot(frappe.get_doc("Quotation", q.name))
		self.assertTrue(snap["valid"])
		titles = [e["title"] for e in snap["sections"]]
		contents = " ".join(e["content"] for e in snap["sections"])
		self.assertIn(QA_MARK, contents, "el renderer consume el contenido editado")
		self.assertIn("UX-A editado", titles)
		self.assertNotIn("UX-C", titles, "la sección eliminada no reaparece")
		self.assertEqual(before, self._snapshot(q.name), "get_sections_snapshot no debe mutar la narrativa")

	# 3) el reorden (D antes de B) se conserva en el lector del PF
	def test_3_reorder_survives_reader(self):
		q = _make_draft(self)
		self._edit_and_save(q.name)
		order = [e["title"] for e in get_sections_snapshot(frappe.get_doc("Quotation", q.name))["sections"]]
		self.assertLess(order.index("UX-D"), order.index("UX-B"), "D reordenada antes de B se conserva")
