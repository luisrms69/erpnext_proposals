# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Pruebas de los campos editoriales opcionales del alcance.

Seis campos Text Editor opcionales en Scope Item (y su copia en Quotation Scope Item):
service_objective, methodology, expected_result, scope_limit, exclusions, acceptance_criteria.

No son Select, no hay tipos de bloque (`block_type`), no son obligatorios y no afectan Tasks,
horas ni costos. Se propagan por el loader, la generación de alcance, el resync y el versionado.
"""

import json
import os
import tempfile
import unittest

import frappe

from erpnext_proposals.erpnext_proposals.catalog_data import catalog_loader
from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import _copy_scope_item
from erpnext_proposals.erpnext_proposals.utils.quotation import (
	_CATALOG_CONTROLLED_FIELDS,
	_EDITORIAL_FIELDS,
)

EDITORIAL = (
	"service_objective",
	"methodology",
	"expected_result",
	"scope_limit",
	"exclusions",
	"acceptance_criteria",
)


class TestScopeEditorialFields(unittest.TestCase):
	def test_01_scope_item_has_six_text_editor_fields(self):
		"""En Scope Item los 6 campos son visibles y editables (no hidden, no read_only)."""
		meta = frappe.get_meta("Scope Item")
		for fn in EDITORIAL:
			f = meta.get_field(fn)
			self.assertIsNotNone(f, f"Scope Item debe tener el campo {fn}")
			self.assertEqual(f.fieldtype, "Text Editor", f"{fn} debe ser Text Editor")
			self.assertFalse(f.hidden, f"{fn} debe ser visible en Scope Item")
			self.assertFalse(f.read_only, f"{fn} debe ser editable en Scope Item")

	def test_02_fields_are_optional(self):
		meta = frappe.get_meta("Scope Item")
		for fn in EDITORIAL:
			self.assertFalse(meta.get_field(fn).reqd, f"{fn} no debe ser obligatorio")

	def test_03_quotation_scope_item_has_editorial_copy(self):
		"""En Quotation Scope Item los 6 campos existen como copia técnica: hidden + read_only."""
		meta = frappe.get_meta("Quotation Scope Item")
		for fn in EDITORIAL:
			f = meta.get_field(fn)
			self.assertIsNotNone(f, f"Quotation Scope Item debe tener el campo {fn}")
			self.assertEqual(f.fieldtype, "Text Editor", f"{fn} debe ser Text Editor")
			self.assertTrue(f.hidden, f"{fn} debe estar oculto en Quotation Scope Item")
			self.assertTrue(f.read_only, f"{fn} debe ser de solo lectura en Quotation Scope Item")

	def test_03b_quotation_scope_item_has_no_editorial_section(self):
		"""No debe existir una sección de captura editorial en Quotation Scope Item."""
		self.assertIsNone(
			frappe.get_meta("Quotation Scope Item").get_field("section_editorial"),
			"Quotation Scope Item NO debe exponer la sección 'Contenido editorial'",
		)

	def test_04_no_block_type_field(self):
		for dt in ("Scope Item", "Quotation Scope Item"):
			self.assertIsNone(frappe.get_meta(dt).get_field("block_type"), f"{dt} NO debe tener block_type")

	def test_05_constants_expose_editorial_fields(self):
		self.assertEqual(tuple(_EDITORIAL_FIELDS), EDITORIAL)
		for fn in EDITORIAL:
			self.assertIn(fn, _CATALOG_CONTROLLED_FIELDS, f"{fn} debe estar controlado por catálogo")

	def test_06_existing_scope_item_without_editorial_saves(self):
		code = "_EDIT-NO-CONTENT"
		try:
			doc = frappe.get_doc(
				{"doctype": "Scope Item", "code": code, "title": "Sin editorial", "sequence": 1}
			).insert(ignore_permissions=True)
			for fn in EDITORIAL:
				self.assertFalse(doc.get(fn), f"{fn} debe quedar vacío por defecto")
		finally:
			if frappe.db.exists("Scope Item", code):
				frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
			frappe.db.commit()  # nosemgrep — limpieza de fixtures de test

	def test_07_copy_scope_item_preserves_editorial(self):
		"""_copy_scope_item (nueva versión de propuesta) conserva los 6 campos editoriales."""
		src = frappe._dict(
			{
				"scope_item": "SC",
				"item_code": "IT",
				"auto_generated": 1,
				"title": "T",
				"code": "C",
				"phase": None,
				"sequence": 10,
				"description": "d",
				"deliverable": "e",
				"activity_type": None,
				"designation": None,
				"estimated_hours": 0,
				"include_in_proposal": 1,
				"service_objective": "<p>obj</p>",
				"methodology": "<p>met</p>",
				"expected_result": "<p>res</p>",
				"scope_limit": "<p>lim</p>",
				"exclusions": "<p>exc</p>",
				"acceptance_criteria": "<p>cri</p>",
			}
		)
		copied = _copy_scope_item(src)
		for fn in EDITORIAL:
			self.assertEqual(copied[fn], src[fn], f"{fn} debe conservarse en la nueva versión")

	def test_08_loader_creates_updates_and_clears_editorial(self):
		"""El loader crea, actualiza y limpia (null explícito) los campos editoriales."""
		code = "_EDIT-LOADER-SC"
		fd, path = tempfile.mkstemp(suffix=".json")
		os.close(fd)

		def _cat(values):
			row = {"code": code, "title": "Editorial loader", "sequence": 10}
			row.update(values)
			return {
				"version": "t",
				"catalog": "demo_editorial",
				"phases": [],
				"sections": [],
				"versioned": [],
				"items": [],
				"scope_items": [row],
				"templates": [],
			}

		try:
			# 1) crear con contenido editorial
			with open(path, "w", encoding="utf-8") as fh:
				json.dump(_cat({f: f"<p>{f}</p>" for f in EDITORIAL}), fh)
			catalog_loader.run(catalog_path=path, dry_run=False)
			for f in EDITORIAL:
				self.assertEqual(frappe.db.get_value("Scope Item", code, f), f"<p>{f}</p>")

			# 2) actualizar contenido
			with open(path, "w", encoding="utf-8") as fh:
				json.dump(_cat({f: f"<p>{f} v2</p>" for f in EDITORIAL}), fh)
			catalog_loader.run(catalog_path=path, dry_run=False, update_content=True)
			for f in EDITORIAL:
				self.assertEqual(frappe.db.get_value("Scope Item", code, f), f"<p>{f} v2</p>")

			# 3) null explícito → limpia
			with open(path, "w", encoding="utf-8") as fh:
				json.dump(_cat({f: None for f in EDITORIAL}), fh)
			catalog_loader.run(catalog_path=path, dry_run=False, update_content=True)
			for f in EDITORIAL:
				self.assertFalse(frappe.db.get_value("Scope Item", code, f), f"{f} debe quedar vacío")
		finally:
			os.remove(path)
			if frappe.db.exists("Scope Item", code):
				frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
			frappe.db.commit()  # nosemgrep — limpieza de fixtures de test
