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
