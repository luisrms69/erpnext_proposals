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

	rendered = frappe.render_template(content, {"doc": doc})

	if any(tag in rendered for tag in _HTML_MARKERS):
		return rendered

	return frappe.utils.markdown(rendered)
