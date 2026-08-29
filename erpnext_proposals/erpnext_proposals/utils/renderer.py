"""Renderer PDF desacoplado y versionado (ADR-0015).

Capa mínima que permite que un Print Format elija su motor de render mediante un **renderer profile**:

    render_proposal_pdf(doc, print_format)
        profile == "legacy" / vacío  → camino actual wkhtmltopdf (intacto; ver print_format.py)
        profile == "gotenberg-v1"    → este módulo (Gotenberg)

El perfil se lee de un único campo genérico en Print Format (``proposal_renderer_profile``). Mientras
ese campo no exista en la metadata (no migrado), todo formato se comporta como ``legacy`` — compat
hacia atrás garantizada.

Camino Gotenberg (conserva la arquitectura de dos renders de ADR-0014):

    cover HTML → cover.pdf            (portada full-bleed, sin header interior)
    body  HTML → body.pdf             (+ header.html / footer.html en contexto Chromium)
    merge(cover.pdf, body.pdf)        (dentro de Gotenberg; pypdf NO participa)

Assets: se inlinan como data-URI (sin fetch HTTP del propio sitio durante el render).
"""

import base64
import mimetypes
import os
import re

import frappe

from erpnext_proposals.erpnext_proposals.utils.gotenberg import GotenbergClient

LEGACY = "legacy"
GOTENBERG_V1 = "gotenberg-v1"

# Campo genérico en Print Format que asocia un formato a su renderer profile.
RENDERER_PROFILE_FIELD = "proposal_renderer_profile"


# ---------------------------------------------------------------------------
# Selección de perfil
# ---------------------------------------------------------------------------
def get_renderer_profile(print_format: str | None) -> str:
	"""Renderer profile de un Print Format. ``legacy`` si no hay formato, el campo no existe aún
	(no migrado) o está vacío — así los formatos actuales siguen por wkhtmltopdf sin cambios."""
	if not print_format:
		return LEGACY
	meta = frappe.get_meta("Print Format")
	if not meta.has_field(RENDERER_PROFILE_FIELD):
		return LEGACY
	return frappe.db.get_value("Print Format", print_format, RENDERER_PROFILE_FIELD) or LEGACY


# ---------------------------------------------------------------------------
# Opciones de página del profile gotenberg-v1 (Letter, portrait, printBackground, scale 1)
# Márgenes en pulgadas. Los del body son valores por defecto razonables para una propuesta con
# letterhead; el ajuste visual fino por formato es actividad de adopción (v2), no de este MVP.
# ---------------------------------------------------------------------------
def _base_page_options() -> dict:
	return {
		"paperWidth": 8.5,  # Letter
		"paperHeight": 11,
		"printBackground": True,
		"scale": 1,
		"landscape": False,  # portrait
	}


def cover_page_options() -> dict:
	"""Portada: márgenes 0 (full-bleed) y solo la primera página (determinista)."""
	return {
		**_base_page_options(),
		"marginTop": 0,
		"marginBottom": 0,
		"marginLeft": 0,
		"marginRight": 0,
		"nativePageRanges": "1",
	}


def body_page_options() -> dict:
	"""Cuerpo: reserva margen superior/inferior para header/footer y márgenes laterales de propuesta."""
	return {
		**_base_page_options(),
		"marginTop": 1.0,
		"marginBottom": 0.7,
		"marginLeft": 0.6,
		"marginRight": 0.6,
	}


# ---------------------------------------------------------------------------
# Inline de assets locales como data-URI (sin fetch HTTP durante el render)
# ---------------------------------------------------------------------------
# Captura ``src="/files/..."`` e ``url(/files/...)`` que apunten a assets locales del site.
_LOCAL_ASSET_RE = re.compile(
	r"""(src=|url\()(['"]?)(/(?:files|private/files|public/files|assets)/[^)'"\s]+)(['"]?)"""
)


def _local_asset_to_data_uri(path: str) -> str:
	"""Resuelve un asset local del site a data-URI base64. ``""`` si no se puede resolver en disco.

	Generaliza el patrón de ``printing.get_logo_data_uri`` a ``/assets/<app>/...`` además de
	``/files`` / ``/private/files`` / ``/public/files``."""
	rel = path.split("?", 1)[0]
	if rel.startswith("/private/files/"):
		fpath = frappe.get_site_path("private", "files", rel[len("/private/files/") :])
	elif rel.startswith("/files/"):
		fpath = frappe.get_site_path("public", "files", rel[len("/files/") :])
	elif rel.startswith("/public/files/"):
		fpath = frappe.get_site_path("public", "files", rel[len("/public/files/") :])
	elif rel.startswith("/assets/"):
		fpath = os.path.join(frappe.local.sites_path, "assets", rel[len("/assets/") :])
	else:
		return ""

	if not os.path.exists(fpath):
		return ""

	mime = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
	with open(fpath, "rb") as fh:  # nosemgrep — lectura local de un asset del propio site
		encoded = base64.b64encode(fh.read()).decode("ascii")
	return f"data:{mime};base64,{encoded}"


def inline_local_assets(html: str) -> str:
	"""Reemplaza referencias a assets locales (``src=`` y ``url()``) por data-URI. Deja intacto lo que
	no resuelva en disco (URLs externas, o rutas no locales)."""

	def _repl(match: "re.Match") -> str:
		prefix, quote_open, path, quote_close = match.groups()
		data_uri = _local_asset_to_data_uri(path)
		if not data_uri:
			return match.group(0)
		return f"{prefix}{quote_open}{data_uri}{quote_close}"

	return _LOCAL_ASSET_RE.sub(_repl, html)


# ---------------------------------------------------------------------------
# Extracción de header/footer y envoltura como documentos completos para Chromium
# ---------------------------------------------------------------------------
def _prepare_fragment(element) -> None:
	"""Ajusta un fragmento header/footer para su contexto Chromium propio: lo hace visible (quita
	``hidden-pdf``/``visible-pdf`` del contenedor), elimina descendientes ``hidden-pdf`` y revela los
	``visible-pdf``. Equivale al ``toggle_visible_pdf`` de Frappe, aplicado al fragmento extraído."""
	if element.get("class"):
		element["class"] = [c for c in element["class"] if c not in ("hidden-pdf", "visible-pdf")]
	for tag in element.find_all(class_="hidden-pdf"):
		tag.extract()
	for tag in element.find_all(class_="visible-pdf"):
		tag["class"] = [c for c in tag.get("class", []) if c != "visible-pdf"]


def extract_header_footer(body_html: str) -> tuple[str, str | None, str | None, str]:
	"""Extrae ``#header-html`` / ``#footer-html`` del HTML del body y los quita del index.

	Devuelve ``(index_html, header_fragment, footer_fragment, styles)`` donde los fragmentos son el
	HTML interno de cada contenedor (o ``None`` si no existe) y ``styles`` concatena los ``<style>``
	del documento para reusarlos en los documentos de header/footer."""
	from bs4 import BeautifulSoup

	soup = BeautifulSoup(body_html, "html5lib")
	styles = "".join(str(s) for s in soup.find_all("style"))

	def _pop(html_id: str) -> str | None:
		element = soup.find(id=html_id)
		if not element:
			return None
		element.extract()
		# Quitar cualquier duplicado remanente del body (mismo id).
		for dup in soup.find_all(id=html_id):
			dup.extract()
		_prepare_fragment(element)
		return element.decode_contents()

	header = _pop("header-html")
	footer = _pop("footer-html")
	return str(soup), header, footer, styles


def wrap_fragment_as_document(fragment_html: str, styles: str = "") -> str:
	"""Envuelve un fragmento header/footer en un documento HTML completo válido para Chromium.

	Chromium (Gotenberg) renderiza header/footer en un contexto propio: no heredan el CSS del body,
	no deben hacer fetch externo y sus imágenes deben ir inline. Aquí se fija ``margin:0`` y un
	``font-size`` explícito (Chromium reduce el header/footer por defecto) y se reinyectan los estilos
	del documento."""
	base_css = (
		"*{-webkit-print-color-adjust:exact;print-color-adjust:exact;}"
		"body{margin:0;padding:0;font-size:8pt;width:100%;}"
	)
	return (
		"<!DOCTYPE html><html><head><meta charset='utf-8'>"
		f"<style>{base_css}</style>{styles}</head><body>{fragment_html}</body></html>"
	)


# ---------------------------------------------------------------------------
# Orquestación Gotenberg (2 renders + merge)
# ---------------------------------------------------------------------------
def render_proposal_pdf_gotenberg(doc, print_format: str) -> bytes:
	"""Genera el PDF de la propuesta vía Gotenberg.

	Si la Proposal Template usa portada separada y es su Print Format comercial: dos renders
	(portada + cuerpo) unidos por el merge de Gotenberg. En otro caso: un único render del cuerpo con
	su header/footer repetido. ``pypdf`` no participa del merge contractual."""
	from frappe import get_print

	from erpnext_proposals.erpnext_proposals.utils.print_format import _uses_separate_cover

	client = GotenbergClient()  # valida el endpoint (fail closed)
	separate_cover = _uses_separate_cover(doc, print_format)

	cover_pdf: bytes | None = None
	try:
		if separate_cover:
			doc.proposal_render_part = "cover"
			cover_html = inline_local_assets(
				get_print(doc.doctype, doc.name, print_format=print_format, doc=doc, no_letterhead=1)
			)
			cover_pdf = client.html_to_pdf(cover_html, options=cover_page_options())
			doc.proposal_render_part = "body"

		body_html = get_print(doc.doctype, doc.name, print_format=print_format, doc=doc)
		index_html, header_frag, footer_frag, styles = extract_header_footer(body_html)
		index_html = inline_local_assets(index_html)
		header_doc = (
			inline_local_assets(wrap_fragment_as_document(header_frag, styles)) if header_frag else None
		)
		footer_doc = (
			inline_local_assets(wrap_fragment_as_document(footer_frag, styles)) if footer_frag else None
		)
		body_pdf = client.html_to_pdf(
			index_html, header_html=header_doc, footer_html=footer_doc, options=body_page_options()
		)
	finally:
		doc.proposal_render_part = None

	if cover_pdf is None:
		return body_pdf
	return client.merge([("cover.pdf", cover_pdf), ("body.pdf", body_pdf)])
