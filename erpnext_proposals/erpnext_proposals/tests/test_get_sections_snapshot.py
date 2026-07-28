# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Pruebas del helper Jinja fail-closed `get_sections_snapshot`.

Valida que la lectura de `doc.proposal_sections_snapshot` nunca lance hacia Jinja, que una sola
entrada inválida invalide todo el snapshot y que no se consulte ningún maestro vivo. Datos ficticios;
sin nombres ni contenido del catálogo privado.
"""

import json
import types
import unittest

import frappe

from erpnext_proposals.erpnext_proposals.utils.printing import get_sections_snapshot


def _entry(**over):
	base = {
		"sequence": 10,
		"title": "Título de sección",
		"content": "<p>Contenido {{ doc.name }}</p>",
		"source_section": "SEC-A",
		"is_executive_summary": 0,
		"captured_on": "2026-07-28T10:00:00",
	}
	base.update(over)
	return base


def _doc(raw):
	return frappe._dict({"proposal_sections_snapshot": raw})


class TestGetSectionsSnapshot(unittest.TestCase):
	# ── snapshot válido ─────────────────────────────────────────────────────

	def test_01_valid_snapshot_returns_valid_true(self):
		res = get_sections_snapshot(_doc(json.dumps([_entry()])))
		self.assertTrue(res["valid"])
		self.assertEqual(res["reason"], "ok")
		self.assertEqual(len(res["sections"]), 1)

	def test_02_sorted_stably_by_sequence(self):
		raw = json.dumps(
			[
				_entry(sequence=600, title="Cierre"),
				_entry(sequence=100, title="Intro"),
				_entry(sequence=300, title="Extra"),
			]
		)
		res = get_sections_snapshot(_doc(raw))
		self.assertTrue(res["valid"])
		self.assertEqual([s["sequence"] for s in res["sections"]], [100, 300, 600])

	def test_02b_stable_order_for_equal_sequence(self):
		raw = json.dumps([_entry(sequence=500, title="A"), _entry(sequence=500, title="B")])
		res = get_sections_snapshot(_doc(raw))
		self.assertEqual([s["title"] for s in res["sections"]], ["A", "B"])

	def test_03_preserves_content_and_extra_properties(self):
		content = "<p>{{ doc.grand_total }} & <b>literal</b></p>"
		raw = json.dumps([_entry(content=content, extra_prop="conservar", is_executive_summary=1)])
		res = get_sections_snapshot(_doc(raw))
		s = res["sections"][0]
		self.assertEqual(s["content"], content)  # sin renderizar ni modificar
		self.assertEqual(s["extra_prop"], "conservar")  # propiedad adicional conservada
		self.assertEqual(s["is_executive_summary"], 1)

	# ── missing (fail-closed) ───────────────────────────────────────────────

	def test_04_missing_field_none_empty_whitespace(self):
		for raw in (None, "", "   ", "\n\t"):
			res = get_sections_snapshot(_doc(raw))
			self.assertFalse(res["valid"])
			self.assertEqual(res["reason"], "missing")
			self.assertEqual(res["sections"], [])

	def test_04b_attribute_absent(self):
		doc = types.SimpleNamespace()  # sin el atributo
		res = get_sections_snapshot(doc)
		self.assertEqual(res["reason"], "missing")

	# ── invalid_json ────────────────────────────────────────────────────────

	def test_05_malformed_json(self):
		for raw in ("[", "[{", '[{"a":}]', "not json", "{bad}"):
			res = get_sections_snapshot(_doc(raw))
			self.assertFalse(res["valid"])
			self.assertEqual(res["reason"], "invalid_json")
			self.assertEqual(res["sections"], [])

	# ── invalid_structure / empty (fail-closed) ─────────────────────────────

	def test_06_non_list_and_empty_list(self):
		# objeto JSON
		res = get_sections_snapshot(_doc(json.dumps({"sequence": 10})))
		self.assertEqual(res["reason"], "invalid_structure")
		# escalar
		res = get_sections_snapshot(_doc(json.dumps(5)))
		self.assertEqual(res["reason"], "invalid_structure")
		res = get_sections_snapshot(_doc(json.dumps("texto")))
		self.assertEqual(res["reason"], "invalid_structure")
		# lista vacía
		res = get_sections_snapshot(_doc(json.dumps([])))
		self.assertFalse(res["valid"])
		self.assertEqual(res["reason"], "empty")

	def test_07_non_dict_entry_fails_closed(self):
		for bad in ("string", 5, ["nested"], None):
			raw = json.dumps([bad])
			res = get_sections_snapshot(_doc(raw))
			self.assertFalse(res["valid"])
			self.assertEqual(res["reason"], "invalid_structure")

	def test_08_each_required_field_missing_fails_closed(self):
		for field in (
			"sequence",
			"title",
			"content",
			"source_section",
			"is_executive_summary",
			"captured_on",
		):
			e = _entry()
			del e[field]
			res = get_sections_snapshot(_doc(json.dumps([e])))
			self.assertFalse(res["valid"], f"faltando {field} debe invalidar")
			self.assertEqual(res["reason"], "invalid_structure")

	def test_09_invalid_types_fail_closed(self):
		bad_entries = [
			_entry(sequence=True),  # boolean no es entero válido
			_entry(sequence="10"),  # string no es entero
			_entry(sequence=1.5),  # float no es entero
			_entry(title=""),  # string vacío
			_entry(title="   "),  # solo espacios
			_entry(title=123),  # no string
			_entry(content=""),  # vacío
			_entry(content=None),  # no string
			_entry(source_section=""),  # vacío
			_entry(source_section=5),  # no string
			_entry(is_executive_summary=2),  # entero fuera de 0/1
			_entry(is_executive_summary="1"),  # string
			_entry(is_executive_summary=None),  # None
			_entry(captured_on=""),  # vacío
			_entry(captured_on=123),  # no string
		]
		for e in bad_entries:
			res = get_sections_snapshot(_doc(json.dumps([e])))
			self.assertFalse(res["valid"], f"entrada inválida debió fallar: {e}")
			self.assertEqual(res["reason"], "invalid_structure")

	def test_10_one_invalid_entry_invalidates_whole_snapshot(self):
		raw = json.dumps([_entry(sequence=10), _entry(sequence=20, title=""), _entry(sequence=30)])
		res = get_sections_snapshot(_doc(raw))
		self.assertFalse(res["valid"])
		self.assertEqual(res["reason"], "invalid_structure")
		self.assertEqual(res["sections"], [])  # nada parcial

	# ── sin maestros vivos ──────────────────────────────────────────────────

	def test_11_never_queries_live_masters(self):
		calls = {"n": 0}

		def _boom(*a, **k):
			calls["n"] += 1
			raise AssertionError("el helper consultó un maestro vivo")

		orig = (frappe.get_doc, frappe.get_all, frappe.db.get_value)
		frappe.get_doc, frappe.get_all, frappe.db.get_value = _boom, _boom, _boom
		try:
			res = get_sections_snapshot(_doc(json.dumps([_entry()])))
		finally:
			frappe.get_doc, frappe.get_all, frappe.db.get_value = orig
		self.assertTrue(res["valid"])
		self.assertEqual(calls["n"], 0)

	# ── nunca lanza ─────────────────────────────────────────────────────────

	def test_12_never_raises_for_unexpected_input(self):
		weird = [
			_doc(123),  # snapshot no-string
			_doc(["ya", "es", "lista"]),  # ya es lista (no string)
			_doc({"a": 1}),  # dict
			_doc(json.dumps([{"sequence": [1, 2]}])),  # tipos raros anidados
			frappe._dict({}),  # sin el campo
		]
		for d in weird:
			try:
				res = get_sections_snapshot(d)
			except Exception as e:
				self.fail(f"el helper lanzó: {e!r}")
			self.assertIn("reason", res)
			self.assertFalse(res["valid"])

	# ── disponible en Jinja vía hooks ───────────────────────────────────────

	def test_13_registered_in_jinja_env(self):
		methods = frappe.get_hooks("jinja").get("methods", [])
		self.assertIn(
			"erpnext_proposals.erpnext_proposals.utils.printing.get_sections_snapshot",
			methods,
		)
		# disponible realmente al renderizar
		out = frappe.render_template(
			"{{ get_sections_snapshot(doc).reason }}",
			{"doc": _doc(None)},
		)
		self.assertEqual(out.strip(), "missing")
		out2 = frappe.render_template(
			"{{ get_sections_snapshot(doc).valid }}|{{ get_sections_snapshot(doc).sections | length }}",
			{"doc": _doc(json.dumps([_entry()]))},
		)
		self.assertEqual(out2.strip(), "True|1")
