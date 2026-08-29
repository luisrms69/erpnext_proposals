# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Pruebas unitarias del renderer desacoplado (ADR-0015): selección de perfil, adapter Gotenberg,
extracción de header/footer, inline de assets y merge en orden. HTTP siempre mockeado — no requieren
una instancia real de Gotenberg ni el Custom Field migrado."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from erpnext_proposals.erpnext_proposals.utils import gotenberg as gb
from erpnext_proposals.erpnext_proposals.utils import renderer as rnd

CONVERT = gb.CHROMIUM_CONVERT_PATH
MERGE = gb.MERGE_PATH


def _resp(status=200, content=b"%PDF-1.4", text="") -> MagicMock:
	r = MagicMock()
	r.status_code = status
	r.content = content
	r.text = text
	return r


class TestRendererProfileSelection(unittest.TestCase):
	def test_no_print_format_is_legacy(self):
		self.assertEqual(rnd.get_renderer_profile(None), rnd.LEGACY)
		self.assertEqual(rnd.get_renderer_profile(""), rnd.LEGACY)

	def test_field_absent_is_legacy(self):
		"""Si el Custom Field aún no existe en metadata (no migrado) → legacy (compat hacia atrás)."""
		meta = MagicMock()
		meta.has_field.return_value = False
		with patch.object(rnd.frappe, "get_meta", return_value=meta):
			self.assertEqual(rnd.get_renderer_profile("Cualquier PF"), rnd.LEGACY)

	def test_empty_value_is_legacy(self):
		meta = MagicMock()
		meta.has_field.return_value = True
		with (
			patch.object(rnd.frappe, "get_meta", return_value=meta),
			patch.object(rnd.frappe.db, "get_value", return_value=None),
		):
			self.assertEqual(rnd.get_renderer_profile("PF sin perfil"), rnd.LEGACY)

	def test_gotenberg_value_selected(self):
		meta = MagicMock()
		meta.has_field.return_value = True
		with (
			patch.object(rnd.frappe, "get_meta", return_value=meta),
			patch.object(rnd.frappe.db, "get_value", return_value="gotenberg-v1"),
		):
			self.assertEqual(rnd.get_renderer_profile("PF Gotenberg"), rnd.GOTENBERG_V1)


class TestDispatch(unittest.TestCase):
	"""El dispatch de `render_proposal_pdf` enruta por perfil sin romper el camino legacy."""

	def test_gotenberg_profile_routes_to_gotenberg(self):
		from erpnext_proposals.erpnext_proposals.utils import print_format as pf

		with (
			patch.object(rnd, "get_renderer_profile", return_value=rnd.GOTENBERG_V1),
			patch.object(rnd, "render_proposal_pdf_gotenberg", return_value=b"%PDF-gotenberg") as m,
		):
			out = pf.render_proposal_pdf(MagicMock(), "PF Gotenberg")
		self.assertEqual(out, b"%PDF-gotenberg")
		m.assert_called_once()

	def test_legacy_profile_does_not_call_gotenberg(self):
		"""Con perfil legacy no se invoca Gotenberg: sigue el camino wkhtmltopdf de siempre."""
		from erpnext_proposals.erpnext_proposals.utils import print_format as pf

		doc = MagicMock()
		doc.doctype = "Quotation"
		doc.name = "QTN-0001"
		with (
			patch.object(rnd, "get_renderer_profile", return_value=rnd.LEGACY),
			patch.object(rnd, "render_proposal_pdf_gotenberg") as m_got,
			patch.object(pf, "_uses_separate_cover", return_value=False),
			patch("frappe.get_print", return_value="<html></html>"),
			patch("frappe.utils.pdf.get_pdf", return_value=b"%PDF-legacy") as m_legacy,
		):
			out = pf.render_proposal_pdf(doc, "Propuesta Comercial")
		m_got.assert_not_called()
		m_legacy.assert_called_once()
		self.assertEqual(out, b"%PDF-legacy")


class TestGotenbergConfig(unittest.TestCase):
	def test_missing_url_fails_closed(self):
		with patch.dict(gb.frappe.conf, {gb.GOTENBERG_CONF_KEY: ""}, clear=False):
			with self.assertRaises(frappe.ValidationError):
				gb.get_gotenberg_url()

	def test_url_trailing_slash_stripped(self):
		with patch.dict(gb.frappe.conf, {gb.GOTENBERG_CONF_KEY: "http://localhost:3000/"}, clear=False):
			self.assertEqual(gb.get_gotenberg_url(), "http://localhost:3000")


class TestGotenbergClient(unittest.TestCase):
	def _client(self) -> gb.GotenbergClient:
		return gb.GotenbergClient(base_url="http://gotenberg:3000")

	def test_html_request_construction(self):
		with patch.object(gb.requests, "post", return_value=_resp()) as post:
			self._client().html_to_pdf(
				"<html>b</html>", options={"paperWidth": 8.5, "printBackground": True, "scale": 1}
			)
		args, kwargs = post.call_args
		self.assertEqual(args[0], f"http://gotenberg:3000{CONVERT}")
		names = [f[1][0] for f in kwargs["files"]]
		self.assertEqual(names, ["index.html"])
		# bool → 'true'; números → string
		self.assertEqual(kwargs["data"]["printBackground"], "true")
		self.assertEqual(kwargs["data"]["paperWidth"], "8.5")
		self.assertEqual(kwargs["data"]["scale"], "1")
		self.assertIn("timeout", kwargs)

	def test_html_includes_header_footer_files(self):
		with patch.object(gb.requests, "post", return_value=_resp()) as post:
			self._client().html_to_pdf("<html>b</html>", header_html="<h></h>", footer_html="<f></f>")
		names = [f[1][0] for f in post.call_args.kwargs["files"]]
		self.assertEqual(names, ["index.html", "header.html", "footer.html"])

	def test_merge_orders_cover_before_body(self):
		with patch.object(gb.requests, "post", return_value=_resp()) as post:
			self._client().merge([("cover.pdf", b"A"), ("body.pdf", b"B")])
		args, kwargs = post.call_args
		self.assertEqual(args[0], f"http://gotenberg:3000{MERGE}")
		names = [f[1][0] for f in kwargs["files"]]
		# prefijo numérico → Gotenberg fusiona cover antes que body
		self.assertEqual(names, ["0_cover.pdf", "1_body.pdf"])

	def test_http_error_raises_no_silent_fallback(self):
		with patch.object(gb.requests, "post", return_value=_resp(status=503, text="unavailable")):
			with self.assertRaises(frappe.ValidationError) as ctx:
				self._client().html_to_pdf("<html>b</html>")
		self.assertIn("503", str(ctx.exception))

	def test_connection_error_raises_no_silent_fallback(self):
		with patch.object(gb.requests, "post", side_effect=gb.requests.ConnectionError("boom")):
			with self.assertRaises(frappe.ValidationError):
				self._client().merge([("cover.pdf", b"A")])


class TestHeaderFooterExtraction(unittest.TestCase):
	BODY = (
		"<html><head><style>.x{color:red}</style></head><body>"
		'<div id="header-html" class="hidden-pdf"><img src="/files/logo.png"></div>'
		"<div class='content'>Cuerpo</div>"
		'<div id="footer-html" class="visible-pdf">Pie</div>'
		"</body></html>"
	)

	def test_extracts_and_removes_header_footer(self):
		index_html, header, footer, styles = rnd.extract_header_footer(self.BODY)
		self.assertIsNotNone(header)
		self.assertIsNotNone(footer)
		self.assertIn("logo.png", header)
		self.assertIn("Pie", footer)
		# ya no están en el index
		self.assertNotIn("header-html", index_html)
		self.assertNotIn("footer-html", index_html)
		self.assertIn("Cuerpo", index_html)
		self.assertIn(".x{color:red}", styles)

	def test_no_header_footer_returns_none(self):
		index_html, header, footer, _ = rnd.extract_header_footer("<html><body>solo cuerpo</body></html>")
		self.assertIsNone(header)
		self.assertIsNone(footer)
		self.assertIn("solo cuerpo", index_html)

	def test_wrap_fragment_is_full_document(self):
		doc = rnd.wrap_fragment_as_document("<div>H</div>", styles="<style>.a{}</style>")
		self.assertTrue(doc.lstrip().startswith("<!DOCTYPE html>"))
		self.assertIn("<div>H</div>", doc)
		self.assertIn(".a{}", doc)


class TestInlineAssets(unittest.TestCase):
	def test_inlines_img_src_local_asset(self):
		html = '<img src="/files/logo.png">'
		with patch.object(rnd, "_local_asset_to_data_uri", return_value="data:image/png;base64,AAAA"):
			out = rnd.inline_local_assets(html)
		self.assertIn('src="data:image/png;base64,AAAA"', out)
		self.assertNotIn("/files/logo.png", out)

	def test_inlines_css_url_local_asset(self):
		html = "<style>.b{background:url(/files/band.png)}</style>"
		with patch.object(rnd, "_local_asset_to_data_uri", return_value="data:image/png;base64,BBBB"):
			out = rnd.inline_local_assets(html)
		self.assertIn("url(data:image/png;base64,BBBB)", out)

	def test_leaves_unresolved_asset_untouched(self):
		html = '<img src="/files/missing.png">'
		with patch.object(rnd, "_local_asset_to_data_uri", return_value=""):
			out = rnd.inline_local_assets(html)
		self.assertEqual(out, html)

	def test_leaves_external_url_untouched(self):
		html = '<img src="https://cdn.example.com/x.png">'
		self.assertEqual(rnd.inline_local_assets(html), html)


class TestGotenbergOrchestration(unittest.TestCase):
	"""Orquestación 2-render + merge, con get_print y el cliente mockeados."""

	def _doc(self):
		doc = MagicMock()
		doc.doctype = "Quotation"
		doc.name = "QTN-0001"
		return doc

	def test_separate_cover_does_two_renders_then_merge(self):
		client = MagicMock()
		client.html_to_pdf.side_effect = [b"COVER", b"BODY"]
		client.merge.return_value = b"FINAL"
		body = '<html><body><div id="header-html">H</div>cuerpo<div id="footer-html">F</div></body></html>'
		with (
			patch.object(rnd, "GotenbergClient", return_value=client),
			patch(
				"erpnext_proposals.erpnext_proposals.utils.print_format._uses_separate_cover",
				return_value=True,
			),
			patch("frappe.get_print", side_effect=["<html>cover</html>", body]),
		):
			out = rnd.render_proposal_pdf_gotenberg(self._doc(), "Propuesta Comercial")
		self.assertEqual(out, b"FINAL")
		self.assertEqual(client.html_to_pdf.call_count, 2)
		merged = client.merge.call_args.args[0]
		self.assertEqual([n for n, _ in merged], ["cover.pdf", "body.pdf"])

	def test_single_render_when_no_separate_cover(self):
		client = MagicMock()
		client.html_to_pdf.return_value = b"BODYONLY"
		with (
			patch.object(rnd, "GotenbergClient", return_value=client),
			patch(
				"erpnext_proposals.erpnext_proposals.utils.print_format._uses_separate_cover",
				return_value=False,
			),
			patch("frappe.get_print", return_value="<html><body>cuerpo</body></html>"),
		):
			out = rnd.render_proposal_pdf_gotenberg(self._doc(), "Rentabilidad Estimada")
		self.assertEqual(out, b"BODYONLY")
		client.merge.assert_not_called()
		self.assertEqual(client.html_to_pdf.call_count, 1)


class TestRendererProfileFieldIsTechnical(unittest.TestCase):
	"""Nivel fixture (sin BD): el Custom Field es metadata TÉCNICA, no un control de usuario.

	`proposal_renderer_profile` asocia el Print Format a su motor HTML→PDF; lo administra el app / el
	loader del pack, no el usuario. Debe ser oculto + read-only (ambas propiedades son de UI y no
	impiden asignarlo programáticamente desde Python/loader)."""

	@classmethod
	def _record(cls) -> dict:
		import json

		fixture = frappe.get_app_path("erpnext_proposals", "fixtures", "custom_field.json")
		with open(fixture, encoding="utf-8") as fh:
			data = json.load(fh)
		return next(r for r in data if r["name"] == "Print Format-proposal_renderer_profile")

	def test_field_is_hidden_and_read_only(self):
		rec = self._record()
		self.assertEqual(rec["hidden"], 1, "el renderer profile no debe ser visible al usuario")
		self.assertEqual(rec["read_only"], 1, "el renderer profile no debe ser editable por el usuario")

	def test_field_definition_preserved(self):
		rec = self._record()
		self.assertEqual(rec["dt"], "Print Format")
		self.assertEqual(rec["fieldtype"], "Select")
		self.assertEqual(rec["options"], "legacy\ngotenberg-v1")
		self.assertEqual(rec["default"], "legacy")


if __name__ == "__main__":
	unittest.main()
