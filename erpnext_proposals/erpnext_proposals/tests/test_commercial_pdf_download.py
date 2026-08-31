# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Pruebas del endpoint de descarga del PDF comercial (`download_commercial_pdf`).

Defecto corregido: el botón "Imprimir Propuesta Comercial" abría `/printview` y saltaba
`render_proposal_pdf()` — por tanto el renderer profile (Gotenberg / legacy, ADR-0015) nunca se
aplicaba. El endpoint fuerza la cadena oficial: `resolve_commercial_print_format` → `render_proposal_pdf`.

Todo mockeado: no requieren Gotenberg real, ni el Custom Field migrado, ni escrituras a BD."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from erpnext_proposals.erpnext_proposals.utils import print_format as pf
from erpnext_proposals.erpnext_proposals.utils import renderer as rnd


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
	"""Ejecuta el endpoint con `frappe.get_doc` y `frappe.local.response` aislados. Devuelve la
	respuesta (un `frappe._dict`) para inspeccionar filename/filecontent/content_type/type."""
	resp = frappe._dict()
	stack = [
		patch.object(pf.frappe, "get_doc", return_value=doc),
		patch("frappe.local.response", resp),
	]
	stack.extend(extra_patches)
	from contextlib import ExitStack

	with ExitStack() as es:
		for p in stack:
			es.enter_context(p)
		pf.download_commercial_pdf(doc.name)
	return resp


class TestDownloadCommercialPdf(unittest.TestCase):
	# A. El endpoint resuelve el Print Format con resolve_commercial_print_format(doc).
	def test_a_uses_resolver(self):
		doc = _doc()
		with (
			patch.object(pf, "resolve_commercial_print_format", return_value="PF X") as m_res,
			patch.object(pf, "render_proposal_pdf", return_value=b"%PDF-1.4"),
		):
			_run(doc)
		m_res.assert_called_once_with(doc)
		doc.check_permission.assert_called_once_with("read")

	# B. Genera los bytes EXCLUSIVAMENTE con render_proposal_pdf(doc, formato_resuelto).
	def test_b_calls_render_proposal_pdf_with_resolved_format(self):
		doc = _doc()
		with (
			patch.object(pf, "resolve_commercial_print_format", return_value="PF Resuelto"),
			patch.object(pf, "render_proposal_pdf", return_value=b"%PDF-bytes") as m_render,
		):
			resp = _run(doc)
		m_render.assert_called_once_with(doc, "PF Resuelto")
		self.assertEqual(resp.filecontent, b"%PDF-bytes")

	# C. Responde como descarga PDF (filename .pdf, content_type application/pdf, type download).
	def test_c_response_is_pdf_download(self):
		doc = _doc(name="SAL-QTN-2026-00013")
		with (
			patch.object(pf, "resolve_commercial_print_format", return_value="PF X"),
			patch.object(pf, "render_proposal_pdf", return_value=b"%PDF-1.4"),
		):
			resp = _run(doc)
		self.assertEqual(resp.type, "download")
		self.assertEqual(resp.content_type, "application/pdf")
		self.assertEqual(resp.filename, "SAL-QTN-2026-00013.pdf")
		self.assertEqual(resp.filecontent, b"%PDF-1.4")

	# D. Propuesta congelada → se usa el proposal_effective_print_format inmutable.
	def test_d_frozen_uses_effective_format(self):
		doc = _doc(effective="Bolsa de Horas v3", template="Bolsa de Horas", override="Otro PF")
		with patch.object(pf, "render_proposal_pdf", return_value=b"%PDF") as m_render:
			_run(doc)
		# resolver real: congelada gana sobre override/template
		m_render.assert_called_once_with(doc, "Bolsa de Horas v3")

	# E. Un PF con perfil gotenberg-v1 llega al dispatcher Gotenberg (por render_proposal_pdf real).
	def test_e_gotenberg_profile_reaches_dispatcher(self):
		doc = _doc(effective="PF Gotenberg")
		with (
			patch.object(rnd, "get_renderer_profile", return_value=rnd.GOTENBERG_V1),
			patch.object(rnd, "render_proposal_pdf_gotenberg", return_value=b"%PDF-got") as m_got,
		):
			resp = _run(doc)
		m_got.assert_called_once_with(doc, "PF Gotenberg")
		self.assertEqual(resp.filecontent, b"%PDF-got")

	# F. Un PF legacy sigue por el camino wkhtmltopdf, sin tocar Gotenberg.
	def test_f_legacy_profile_stays_legacy(self):
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


class TestCommercialButtonJS(unittest.TestCase):
	"""Verifica el flujo del botón en quotation.js sin ejecutar JS (lectura de fuente)."""

	@classmethod
	def setUpClass(cls):
		path = frappe.get_app_path("erpnext_proposals", "public", "js", "quotation.js")
		with open(path, encoding="utf-8") as fh:
			cls.js = fh.read()
		cls.i_com = cls.js.index("Imprimir Propuesta Comercial")
		cls.i_rent = cls.js.index("Imprimir Rentabilidad Estimada")

	# G. El botón comercial ya NO abre /printview: usa el endpoint download_commercial_pdf.
	# (Se comprueba que NO construya la URL /printview? ni llame window.open — la palabra puede
	# aparecer en un comentario, lo que importa es que no haya navegación a printview.)
	def test_g_commercial_button_no_printview(self):
		block = self.js[self.i_com : self.i_rent]
		self.assertIn("download_commercial_pdf", block)
		self.assertNotIn("/printview?", block)
		self.assertNotIn("window.open", block)

	# H. El botón de Rentabilidad Estimada queda intacto (printview + window.open).
	def test_h_rentabilidad_button_unchanged(self):
		block = self.js[self.i_rent : self.i_rent + 800]
		self.assertIn("/printview", block)
		self.assertIn("Rentabilidad%20Estimada", block)
		self.assertIn("window.open", block)
		self.assertNotIn("download_commercial_pdf", block)


if __name__ == "__main__":
	unittest.main()
