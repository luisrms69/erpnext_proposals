import base64
import json
import mimetypes
import os

import frappe

_HTML_MARKERS = (
	"<p>",
	"<p ",
	"<table",
	"<ul>",
	"<ol>",
	"<li>",
	"<div>",
	"<div ",
	"<h1>",
	"<h2>",
	"<h3>",
	"<strong>",
	"<em>",
	"<b>",
	"<i>",
	"<br>",
	"<br/>",
)


def render_section_content(content: str, doc) -> str:
	"""
	Renders Proposal Section content for Print Formats.

	Pipeline:
	  1. frappe.render_template → substitutes {{ doc.x }} variables
	  2. Detects whether the result is HTML or plain text / Markdown
	  3. HTML path  → use as-is (primary: WYSIWYG / Text Editor output)
	  4. Plain path → frappe.utils.markdown to convert bullets / paragraphs
	  5. Returns the HTML string; caller should use | safe

	Registered in hooks.py under jinja.methods so it is available
	in all Print Format and Email Template contexts.
	"""
	if not content:
		return ""

	rendered = frappe.render_template(content, {"doc": doc})  # nosemgrep

	if any(tag in rendered for tag in _HTML_MARKERS):
		return rendered

	return frappe.utils.markdown(rendered)


def parse_json(val) -> list:
	"""Wrapper around frappe.parse_json for Jinja sandbox (module attrs are restricted)."""
	return frappe.parse_json(val) or []


def keep_headings_with_next(html: str) -> str:
	"""Envuelve cada heading (h1-h6) junto con su siguiente elemento hermano en un contenedor
	``page-break-inside: avoid``, para que un título/subtítulo no quede huérfano al final de una página.

	wkhtmltopdf (WebKit) IGNORA ``page-break-after: avoid`` en headings, pero SÍ respeta
	``page-break-inside: avoid`` en un bloque: por eso el "keep-with-next" se materializa como estructura,
	no como propiedad del heading. Es GENÉRICO (por etiqueta de heading, sin nombres ni números de
	sección) y no lanza: ante cualquier problema devuelve el HTML original. Registrado como jinja method.
	"""
	if not html:
		return html
	try:
		from bs4 import BeautifulSoup

		soup = BeautifulSoup(html, "html.parser")
		for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
			# Si ya está dentro de un keep-with-next (p. ej. dos headings consecutivos), no re-envolver.
			if h.find_parent("div", class_="keep-with-next"):
				continue
			nxt = h.find_next_sibling()
			while nxt is not None and getattr(nxt, "name", None) is None:
				nxt = nxt.find_next_sibling()
			if nxt is None:
				continue
			wrapper = soup.new_tag("div")
			wrapper["class"] = "keep-with-next"
			h.insert_before(wrapper)
			wrapper.append(h.extract())
			wrapper.append(nxt.extract())
		return str(soup)
	except Exception:
		return html


# Campos editoriales propios del Item (custom fields) que definen el "Item de servicio" de la propuesta.
_ITEM_EDITORIAL_FIELDS = (
	"proposal_methodology",
	"proposal_expected_result",
	"proposal_scope_limit",
)


def service_item(doc):
	"""Devuelve el Quotation Item de servicio de esta propuesta, de forma GENÉRICA (sin hardcodear
	ningún item_code). Reglas, en orden:

	1. Asociación por alcance: si existe **exactamente un** Item cuya ``item_code`` aparece en
	   ``quotation_scope_items`` (vínculo Scope Item.erpnext_item → Quotation Scope Item), se usa ese.
	2. Fallback: si no hay asociación por alcance pero existe **exactamente un** Item con campos
	   editoriales propios poblados (``proposal_methodology``/``proposal_expected_result``/
	   ``proposal_scope_limit``), se usa ese.
	3. Ambigüedad: si hay varios candidatos o ninguno, devuelve ``None`` (el Print Format no elige
	   arbitrariamente ni inventa).

	Registrado como jinja method: en el contenido de Sections/PF, ``{% set svc = service_item(doc) %}``.
	"""
	items = list(getattr(doc, "items", None) or [])
	if not items:
		return None

	scope_codes = {
		r.item_code
		for r in (getattr(doc, "quotation_scope_items", None) or [])
		if getattr(r, "item_code", None)
	}
	scoped = [it for it in items if getattr(it, "item_code", None) in scope_codes]
	if len(scoped) == 1:
		return scoped[0]

	editorial = [
		it for it in items if any((getattr(it, f, None) or "").strip() for f in _ITEM_EDITORIAL_FIELDS)
	]
	if len(editorial) == 1:
		return editorial[0]

	return None


def _visible_chapter_names(doc) -> list:
	"""Nombres (``section_name``/``source_section``) de los capítulos VISIBLES en el MISMO orden que
	usan el índice y los títulos del Print Format: secciones con ``hide_title=0`` y contenido,
	ordenadas por ``sequence``. Front-matter (``hide_title=1``) queda fuera del 1..N.

	Usa el snapshot congelado si existe; si no, el Template vivo. No lanza."""
	raw = getattr(doc, "proposal_sections_snapshot", None)
	if raw:
		try:
			data = json.loads(raw)
		except _JSON_ERRORS:
			data = []
		rows = [
			d
			for d in data
			if isinstance(d, dict)
			and not int(d.get("hide_title", 0) or 0)
			and (d.get("content") or "").strip()
		]
		rows.sort(key=lambda d: d.get("sequence") or 0)
		return [d.get("source_section") for d in rows]

	if not getattr(doc, "proposal_template", None):
		return []
	tmpl = frappe.get_doc("Proposal Template", doc.proposal_template)
	rows = []
	for row in tmpl.sections:
		ps = frappe.get_cached_doc("Proposal Section", row.proposal_section)
		if not ps.enabled:
			continue
		content = row.custom_content if row.use_custom_content else ps.content
		if not content:
			continue
		if int(row.hide_title or 0):
			continue
		rows.append((row.sequence or 0, ps.section_name))
	rows.sort(key=lambda x: x[0])
	return [name for _, name in rows]


def section_number(doc, section_identifier) -> str:
	"""Número de capítulo (1..N) de la Section indicada por su ``section_name``, derivado del MISMO
	conjunto ordenado que usan el índice y los títulos. Devuelve '' si no está visible/existe, de modo
	que las referencias cruzadas ("sección {{ section_number(doc, 'X') }}") sean siempre dinámicas.

	Registrado como jinja method para usarse en contenido de Sections y Print Formats."""
	names = _visible_chapter_names(doc)
	for i, name in enumerate(names, start=1):
		if name == section_identifier:
			return str(i)
	return ""


# Excepciones que puede lanzar json.loads (ValueError incluye JSONDecodeError; TypeError si el valor no
# es str/bytes). Se declara como constante nombrada para evitar la tupla literal en el `except`, cuya
# forma con/sin paréntesis es inestable entre versiones de ruff-format.
_JSON_ERRORS = (ValueError, TypeError)

# Campos obligatorios de cada entrada del snapshot de secciones (ver utils/quotation._build_sections_snapshot).
_SNAPSHOT_REQUIRED_FIELDS = (
	"sequence",
	"title",
	"content",
	"source_section",
	"is_executive_summary",
	"captured_on",
)


def _is_nonempty_str(val) -> bool:
	return isinstance(val, str) and bool(val.strip())


def _valid_snapshot_entry(entry) -> bool:
	"""True solo si la entrada tiene la estructura mínima y tipos correctos. No lanza."""
	if not isinstance(entry, dict):
		return False
	for field in _SNAPSHOT_REQUIRED_FIELDS:
		if field not in entry:
			return False
	# sequence: entero, nunca boolean
	seq = entry["sequence"]
	if isinstance(seq, bool) or not isinstance(seq, int):
		return False
	# strings no vacíos
	if not _is_nonempty_str(entry["title"]):
		return False
	if not _is_nonempty_str(entry["content"]):
		return False
	if not _is_nonempty_str(entry["source_section"]):
		return False
	if not _is_nonempty_str(entry["captured_on"]):
		return False
	# is_executive_summary: boolean o entero 0/1
	ies = entry["is_executive_summary"]
	if isinstance(ies, bool):
		pass
	elif isinstance(ies, int) and ies in (0, 1):
		pass
	else:
		return False
	return True


def get_sections_snapshot(doc) -> dict:
	"""Lectura fail-closed de ``proposal_sections_snapshot`` para Print Formats.

	Devuelve SIEMPRE ``{"valid": bool, "reason": str, "sections": list}`` y NUNCA lanza hacia Jinja,
	de modo que el Print Format pueda mostrar una advertencia técnica limpia en vez de un PDF roto.

	NO consulta maestros vivos (Proposal Template / Proposal Section / Item / etc.), NO renderiza ni
	modifica el Jinja almacenado en ``content`` y NO reconstruye datos faltantes. Una sola entrada
	inválida invalida TODO el snapshot (sin descartes silenciosos).

	``reason`` (estable, sin datos sensibles): ``missing`` | ``invalid_json`` | ``invalid_structure`` |
	``empty`` | ``ok``. Cuando es válido, las entradas se devuelven completas (conservando propiedades
	adicionales) y ordenadas de forma estable por ``sequence``.
	"""
	raw = getattr(doc, "proposal_sections_snapshot", None)

	if raw is None or not isinstance(raw, str) or not raw.strip():
		return {"valid": False, "reason": "missing", "sections": []}

	try:
		data = json.loads(raw)
	except _JSON_ERRORS:
		return {"valid": False, "reason": "invalid_json", "sections": []}

	if not isinstance(data, list):
		return {"valid": False, "reason": "invalid_structure", "sections": []}

	if len(data) == 0:
		return {"valid": False, "reason": "empty", "sections": []}

	for entry in data:
		if not _valid_snapshot_entry(entry):
			return {"valid": False, "reason": "invalid_structure", "sections": []}

	# sorted() es estable: entradas con igual sequence conservan su orden original.
	sections = sorted(data, key=lambda e: e["sequence"])
	return {"valid": True, "reason": "ok", "sections": sections}


def get_logo_url(logo_path: str) -> str:
	"""
	Return an absolute URL for the logo image suitable for wkhtmltopdf.

	Uses frappe.utils.get_url to build the absolute URL (includes port when
	developer_mode is active). Private files return empty string — wkhtmltopdf
	cannot authenticate private endpoints.
	"""
	if not logo_path:
		return ""

	if logo_path.startswith("/private/"):
		return ""

	from urllib.parse import quote

	return frappe.utils.get_url(quote(logo_path, safe="/"))


def get_logo_data_uri(logo_path: str) -> str:
	"""
	Return a base64 ``data:`` URI for a logo/image stored in the site's files,
	suitable for embedding directly into a Print Format.

	Reads the file from disk (site public/private files) and inlines it, so the
	image renders identically in the browser preview and in the wkhtmltopdf PDF
	WITHOUT an HTTP round-trip. This avoids the common failure where wkhtmltopdf
	cannot reach the app URL (wrong port / host / server down) and the logo shows
	as a broken-image placeholder.

	Accepts a Company logo path such as ``/files/logo.png`` or
	``/private/files/logo.png``. Returns ``""`` when the path is empty or the file
	cannot be resolved on disk (caller should guard the ``<img>`` accordingly).
	"""
	if not logo_path:
		return ""

	rel = logo_path.split("?", 1)[0]
	if rel.startswith("/private/files/"):
		fpath = frappe.get_site_path("private", "files", rel[len("/private/files/") :])
	elif rel.startswith("/files/"):
		fpath = frappe.get_site_path("public", "files", rel[len("/files/") :])
	elif rel.startswith("/public/files/"):
		fpath = frappe.get_site_path("public", "files", rel[len("/public/files/") :])
	else:
		return ""

	if not os.path.exists(fpath):
		return ""

	mime = mimetypes.guess_type(fpath)[0] or "image/png"
	with open(fpath, "rb") as fh:  # nosemgrep — lectura local de un asset del propio site
		encoded = base64.b64encode(fh.read()).decode("ascii")
	return f"data:{mime};base64,{encoded}"
