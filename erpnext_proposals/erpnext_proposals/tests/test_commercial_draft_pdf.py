# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Pruebas del **PDF BORRADOR** de la Propuesta Comercial (v0.11.4) y de la preservación del preview HTML.

Contexto: v0.11.4 = v0.11.2 + una capacidad nueva. El botón *Imprimir Propuesta Comercial* vuelve a su
comportamiento de v0.11.2 (resuelve el PF efectivo → `/printview` → `window.open`, revisión HTML). Se
añade un botón SEPARADO *Descargar PDF Borrador* — solo en Borrador — que descarga un PDF no oficial
generado por `render_proposal_pdf()` con nombre prefijado ``BORRADOR``, sin adjuntar, congelar ni
cambiar de estado. El flujo formal (En Revisión → attach) NO se toca.

Todo mockeado: no requieren Gotenberg real, ni el Custom Field migrado, ni escrituras a BD."""

import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import frappe

from erpnext_proposals.erpnext_proposals.utils import print_format as pf
from erpnext_proposals.erpnext_proposals.utils import renderer as rnd

DRAFT_ENDPOINT = "download_commercial_draft_pdf"


def _doc(name="SAL-QTN-0001", effective=None, template=None, override=None):
	"""Quotation mock con solo los campos que consume el resolver."""
	doc = MagicMock()
	doc.doctype = "Quotation"
	doc.name = name
	values = {
		"proposal_effective_print_format": effective,
		"proposal_print_format": override,
		"proposal_template": template,
	}
	doc.get.side_effect = lambda k, default=None: values.get(k, default)
	return doc


def _run(doc, extra_patches=()):
	"""Ejecuta el endpoint con `frappe.get_doc` y `frappe.local.response` aislados."""
	resp = frappe._dict()
	with ExitStack() as es:
		es.enter_context(patch.object(pf.frappe, "get_doc", return_value=doc))
		es.enter_context(patch("frappe.local.response", resp))
		for p in extra_patches:
			es.enter_context(p)
		pf.download_commercial_draft_pdf(doc.name)
	return resp


class TestDraftEndpoint(unittest.TestCase):
	# B. Requiere permiso de lectura y resuelve con resolve_commercial_print_format.
	def test_requires_read_permission_and_resolver(self):
		doc = _doc()
		with (
			patch.object(pf, "resolve_commercial_print_format", return_value="PF X") as m_res,
			patch.object(pf, "render_proposal_pdf", return_value=b"%PDF-1.4"),
		):
			_run(doc)
		doc.check_permission.assert_called_once_with("read")
		m_res.assert_called_once_with(doc)

	# B. Genera EXCLUSIVAMENTE con render_proposal_pdf(doc, formato_resuelto).
	def test_generates_only_with_render_proposal_pdf(self):
		doc = _doc()
		with (
			patch.object(pf, "resolve_commercial_print_format", return_value="PF Resuelto"),
			patch.object(pf, "render_proposal_pdf", return_value=b"%PDF-bytes") as m_render,
		):
			resp = _run(doc)
		m_render.assert_called_once_with(doc, "PF Resuelto")
		self.assertEqual(resp.filecontent, b"%PDF-bytes")

	# B. Respuesta application/pdf de descarga, filename con "BORRADOR" y el nombre de la Quotation.
	def test_response_is_pdf_download_with_borrador_filename(self):
		doc = _doc(name="SAL-QTN-2026-00013")
		with (
			patch.object(pf, "resolve_commercial_print_format", return_value="PF X"),
			patch.object(pf, "render_proposal_pdf", return_value=b"%PDF-1.4"),
		):
			resp = _run(doc)
		self.assertEqual(resp.type, "download")
		self.assertEqual(resp.content_type, "application/pdf")
		self.assertIn("BORRADOR", resp.filename)
		self.assertIn("SAL-QTN-2026-00013", resp.filename)
		self.assertTrue(resp.filename.endswith(".pdf"))
		# El filename NO debe ser el del documento formal (solo el nombre de la Quotation).
		self.assertNotEqual(resp.filename, "SAL-QTN-2026-00013.pdf")

	# B. NO adjunta, NO crea File, NO cambia estado, NO congela, NO invoca el flujo formal.
	def test_does_not_attach_freeze_or_change_state(self):
		doc = _doc(name="SAL-QTN-0002")
		with (
			patch.object(pf, "resolve_commercial_print_format", return_value="PF X"),
			patch.object(pf, "render_proposal_pdf", return_value=b"%PDF"),
		):
			resp = _run(doc)
		# El endpoint solo lee el doc y arma la respuesta: nada de persistencia/estado.
		doc.save.assert_not_called()
		doc.db_set.assert_not_called()
		doc.submit.assert_not_called()
		doc.run_method.assert_not_called()
		# No existe atributo attach_proposal_pdfs en el módulo print_format (pertenece a utils/quotation).
		self.assertFalse(hasattr(pf, "attach_proposal_pdfs"))
		self.assertEqual(resp.filecontent, b"%PDF")

	# C. Un PF con perfil gotenberg-v1 llega al dispatcher Gotenberg (por render_proposal_pdf real).
	def test_gotenberg_profile_reaches_dispatcher(self):
		doc = _doc(effective="PF Gotenberg")
		with (
			patch.object(rnd, "get_renderer_profile", return_value=rnd.GOTENBERG_V1),
			patch.object(rnd, "render_proposal_pdf_gotenberg", return_value=b"%PDF-got") as m_got,
		):
			resp = _run(doc)
		m_got.assert_called_once_with(doc, "PF Gotenberg")
		self.assertEqual(resp.filecontent, b"%PDF-got")

	# C. Un PF legacy conserva el camino wkhtmltopdf, sin tocar Gotenberg.
	def test_legacy_profile_stays_legacy(self):
		doc = _doc(effective="Propuesta Comercial")
		with (
			patch.object(rnd, "get_renderer_profile", return_value=rnd.LEGACY),
			patch.object(rnd, "render_proposal_pdf_gotenberg") as m_got,
			patch.object(pf, "_uses_separate_cover", return_value=False),
			patch("frappe.get_print", return_value="<html></html>"),
			patch("frappe.utils.pdf.get_pdf", return_value=b"%PDF-legacy") as m_legacy,
		):
			resp = _run(doc)
		m_got.assert_not_called()
		m_legacy.assert_called_once()
		self.assertEqual(resp.filecontent, b"%PDF-legacy")

	# El nombre viejo de v0.11.3 no debe existir ya en el módulo.
	def test_old_v0113_endpoint_removed(self):
		self.assertFalse(hasattr(pf, "download_commercial_pdf"))
		self.assertTrue(hasattr(pf, "download_commercial_draft_pdf"))


class TestButtonsJS(unittest.TestCase):
	"""Verifica los dos botones en quotation.js leyendo la fuente (sin ejecutar JS)."""

	@classmethod
	def setUpClass(cls):
		path = frappe.get_app_path("erpnext_proposals", "public", "js", "quotation.js")
		with open(path, encoding="utf-8") as fh:
			cls.js = fh.read()
		cls.i_com = cls.js.index("Vista previa comercial")
		cls.i_rent = cls.js.index("Vista previa rentabilidad")

	# A. El botón comercial recupera el preview HTML de v0.11.2 (get_effective → /printview → window.open).
	def test_a_commercial_button_is_html_preview(self):
		block = self.js[self.i_com : self.i_rent]
		self.assertIn("get_effective_commercial_print_format", block)
		self.assertIn("/printview?", block)
		self.assertIn("window.open", block)
		# El botón comercial NO debe descargar el PDF borrador.
		self.assertNotIn(DRAFT_ENDPOINT, block)

	# A. El botón de Rentabilidad Estimada queda intacto (printview + window.open).
	def test_a_rentabilidad_button_unchanged(self):
		block = self.js[self.i_rent : self.i_rent + 400]
		self.assertIn("/printview?", block)
		self.assertIn("Rentabilidad%20Estimada", block)
		self.assertIn("window.open", block)

	# B. Existe un botón separado "Descargar PDF comercial", solo en Borrador, que llama al endpoint borrador.
	def test_b_draft_button_only_in_borrador(self):
		self.assertIn("Descargar PDF comercial", self.js)
		i_draft = self.js.index("Descargar PDF comercial")
		# Guarda de estado inmediatamente arriba del botón.
		guard = self.js[max(0, i_draft - 400) : i_draft]
		self.assertIn('workflow_state === "Borrador"', guard)
		self.assertIn("docstatus === 0", guard)
		# El botón usa el endpoint del app (server-side), no construye /printview.
		block = self.js[i_draft : i_draft + 400]
		self.assertIn(DRAFT_ENDPOINT, block)
		self.assertIn("open_url_post", block)
		self.assertNotIn("/printview", block)

	# El nombre de endpoint viejo de v0.11.3 no debe quedar en el JS.
	def test_no_stale_v0113_endpoint_in_js(self):
		self.assertNotIn("download_commercial_pdf", self.js)


if __name__ == "__main__":
	unittest.main()
