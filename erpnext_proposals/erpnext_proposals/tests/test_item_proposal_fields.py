# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Pruebas del rediseño de campos de propuesta en el alcance.

Se RETIRARON los 6 campos editoriales de Scope Item y Quotation Scope Item (y su Section Break),
y en su lugar se declaran 3 Custom Fields opcionales sobre el DocType nativo Item
(`proposal_methodology`, `proposal_expected_result`, `proposal_scope_limit`) más un Section Break
de agrupación (`proposal_content_section`), en `fixtures/custom_field.json`. No debe existir `block_type`.

Los tests a nivel FIXTURE (parseo de JSON del app + hooks) corren siempre. Los de METADATA requieren
que `bench migrate` haya sincronizado el rediseño; se omiten (skip) mientras el site no esté migrado.
"""

import json
import unittest

import frappe

# Campos editoriales retirados (ya no deben existir en los doctypes de alcance).
REMOVED_FIELDS = (
	"service_objective",
	"methodology",
	"expected_result",
	"scope_limit",
	"exclusions",
	"acceptance_criteria",
)
# Nuevos Custom Fields sobre Item.
ITEM_FIELDS = ("proposal_methodology", "proposal_expected_result", "proposal_scope_limit")
ITEM_SECTION = "proposal_content_section"
# Copia técnica de los 3 campos en la línea nativa Quotation Item (hidden + read_only).
QITEM_TECH_FIELDS = ("proposal_methodology", "proposal_expected_result", "proposal_scope_limit")


def _fixture_records():
	path = frappe.get_app_path("erpnext_proposals", "fixtures", "custom_field.json")
	with open(path, encoding="utf-8") as fh:
		return json.load(fh)


def _doctype_field_order(module_folder):
	path = frappe.get_app_path(
		"erpnext_proposals", "erpnext_proposals", "doctype", module_folder, f"{module_folder}.json"
	)
	with open(path, encoding="utf-8") as fh:
		return json.load(fh).get("field_order", [])


def _migrated():
	"""True si migrate ya aplicó el rediseño (Scope Item sin editorial + Item con los 3 campos)."""
	return (
		frappe.get_meta("Scope Item").get_field("service_objective") is None
		and frappe.get_meta("Item").get_field("proposal_methodology") is not None
	)


class TestItemProposalFields(unittest.TestCase):
	# ── Fixture-level (siempre corren; no requieren migrate) ─────────────────────

	def test_fixture_declares_three_item_text_editor_fields(self):
		by_name = {f["name"]: f for f in _fixture_records()}
		for fn in ITEM_FIELDS:
			rec = by_name.get(f"Item-{fn}")
			self.assertIsNotNone(rec, f"Falta el Custom Field Item-{fn} en el fixture")
			self.assertEqual(rec["dt"], "Item")
			self.assertEqual(rec["fieldtype"], "Text Editor")
			self.assertEqual(rec["fieldname"], fn)
			self.assertEqual(rec.get("reqd", 0), 0, f"{fn} debe ser opcional")

	def test_fixture_names_are_unique_and_namespaced(self):
		names = [f["name"] for f in _fixture_records()]
		self.assertEqual(len(names), len(set(names)), "Nombres de Custom Field duplicados")
		for fn in ITEM_FIELDS:
			self.assertIn(f"Item-{fn}", names)

	def test_fixture_insert_after_chain(self):
		by_name = {f["name"]: f for f in _fixture_records()}
		self.assertEqual(by_name["Item-proposal_content_section"]["insert_after"], "description")
		self.assertEqual(by_name["Item-proposal_methodology"]["insert_after"], "proposal_content_section")
		self.assertEqual(by_name["Item-proposal_expected_result"]["insert_after"], "proposal_methodology")
		self.assertEqual(by_name["Item-proposal_scope_limit"]["insert_after"], "proposal_expected_result")

	def test_fixture_declares_quotation_item_technical_fields(self):
		"""Copia técnica en la línea nativa Quotation Item: Text Editor, hidden, read_only, no_copy=0."""
		by_name = {f["name"]: f for f in _fixture_records()}
		for fn in QITEM_TECH_FIELDS:
			rec = by_name.get(f"Quotation Item-{fn}")
			self.assertIsNotNone(rec, f"Falta el Custom Field Quotation Item-{fn} en el fixture")
			self.assertEqual(rec["dt"], "Quotation Item")
			self.assertEqual(rec["fieldtype"], "Text Editor")
			self.assertEqual(rec["hidden"], 1, f"{fn} debe estar oculto en Quotation Item")
			self.assertEqual(rec["read_only"], 1, f"{fn} debe ser read_only en Quotation Item")
			self.assertEqual(
				rec.get("no_copy", 0), 0, f"{fn}: no_copy=0 para conservarlo al duplicar/versionar"
			)
			self.assertEqual(rec.get("reqd", 0), 0, f"{fn} debe ser opcional")

	def test_no_editorial_or_block_type_in_scope_doctypes(self):
		for folder in ("scope_item", "quotation_scope_item"):
			order = set(_doctype_field_order(folder))
			for fn in (*REMOVED_FIELDS, "section_editorial", "block_type"):
				self.assertNotIn(fn, order, f"{fn} no debe existir en {folder}.json")

	def test_hooks_filter_includes_item_fields(self):
		from erpnext_proposals import hooks

		cf = next(f for f in hooks.fixtures if f.get("doctype") == "Custom Field")
		dt_filter = next(c for c in cf["filters"] if c[0] == "dt")[2]
		fn_filter = next(c for c in cf["filters"] if c[0] == "fieldname")[2]
		self.assertIn("Item", dt_filter)
		self.assertIn("Quotation Item", dt_filter)
		for fn in (ITEM_SECTION, *ITEM_FIELDS):
			self.assertIn(fn, fn_filter, f"hooks.py debe filtrar el fieldname {fn}")

	def test_fixture_hooks_consistency(self):
		"""Consistencia fixture ↔ hooks (sin BD ni export-fixtures): cada Custom Field del fixture
		queda incluido por el filtro; el filtro no lista fieldnames inexistentes; y el filtro restringe
		por `dt`+`fieldname` (un filtro solo por dt capturaría Custom Fields de otras apps sobre
		DocTypes compartidos como Item)."""
		from erpnext_proposals import hooks

		cf = next(f for f in hooks.fixtures if f.get("doctype") == "Custom Field")
		conds = {c[0]: c[2] for c in cf["filters"]}
		self.assertIn("dt", conds, "El filtro Custom Field debe restringir por dt")
		self.assertIn("fieldname", conds, "El filtro Custom Field debe restringir por fieldname")
		dts, fns = set(conds["dt"]), list(conds["fieldname"])

		records = _fixture_records()
		fx_pairs = {(r["dt"], r["fieldname"]) for r in records}
		fx_fieldnames = {r["fieldname"] for r in records}
		fx_dts = {r["dt"] for r in records}

		outside = sorted((dt, fn) for (dt, fn) in fx_pairs if not (dt in dts and fn in fns))
		self.assertEqual(outside, [], f"Registros del fixture fuera del filtro: {outside}")

		ghost_fn = sorted(fn for fn in fns if fn not in fx_fieldnames)
		self.assertEqual(ghost_fn, [], f"Fieldnames del filtro inexistentes en el fixture: {ghost_fn}")

		ghost_dt = sorted(dt for dt in dts if dt not in fx_dts)
		self.assertEqual(ghost_dt, [], f"dt del filtro sin registros en el fixture: {ghost_dt}")

		self.assertEqual(len(fns), len(set(fns)), "Fieldnames duplicados en el filtro de hooks")

	def test_copy_item_preserves_proposal_fields_from_row(self):
		"""Versionado: `_copy_item` conserva los cuatro valores (description + proposal_*) DESDE la
		línea anterior (Quotation Item); nunca relee el Item maestro (solo lee el row recibido)."""
		from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import _copy_item

		row = frappe._dict(
			{
				"item_code": "IT",
				"item_name": "N",
				"description": "<p>d</p>",
				"qty": 1,
				"uom": "Nos",
				"rate": 10,
				"price_list_rate": 10,
				"discount_percentage": 0,
				"item_tax_template": None,
				"warehouse": None,
				"proposal_methodology": "<p>m</p>",
				"proposal_expected_result": "<p>r</p>",
				"proposal_scope_limit": "<p>l</p>",
			}
		)
		copied = _copy_item(row)
		self.assertEqual(copied["description"], "<p>d</p>")
		self.assertEqual(copied["proposal_methodology"], "<p>m</p>")
		self.assertEqual(copied["proposal_expected_result"], "<p>r</p>")
		self.assertEqual(copied["proposal_scope_limit"], "<p>l</p>")

	# ── Metadata-level (requieren bench migrate del rediseño) ────────────────────

	def test_meta_item_has_three_optional_text_editors(self):
		if not _migrated():
			self.skipTest("requiere bench migrate del rediseño")
		meta = frappe.get_meta("Item")
		for fn in ITEM_FIELDS:
			f = meta.get_field(fn)
			self.assertIsNotNone(f, f"Item debe tener {fn} tras migrate")
			self.assertEqual(f.fieldtype, "Text Editor")
			self.assertFalse(f.reqd, f"{fn} debe ser opcional")

	def test_meta_item_field_order_follows_insert_after(self):
		if not _migrated():
			self.skipTest("requiere bench migrate del rediseño")
		fieldnames = [f.fieldname for f in frappe.get_meta("Item").fields]
		i_sec = fieldnames.index(ITEM_SECTION)
		i_met = fieldnames.index("proposal_methodology")
		i_res = fieldnames.index("proposal_expected_result")
		i_lim = fieldnames.index("proposal_scope_limit")
		self.assertTrue(i_sec < i_met < i_res < i_lim, "El orden debe seguir insert_after")

	def test_meta_scope_doctypes_have_no_editorial_or_block_type(self):
		if not _migrated():
			self.skipTest("requiere bench migrate del rediseño")
		for dt in ("Scope Item", "Quotation Scope Item"):
			meta = frappe.get_meta(dt)
			for fn in (*REMOVED_FIELDS, "block_type"):
				self.assertIsNone(meta.get_field(fn), f"{dt} no debe tener {fn} tras migrate")

	def test_meta_quotation_item_fields_hidden_readonly(self):
		if not _migrated():
			self.skipTest("requiere bench migrate del rediseño")
		meta = frappe.get_meta("Quotation Item")
		for fn in QITEM_TECH_FIELDS:
			f = meta.get_field(fn)
			self.assertIsNotNone(f, f"Quotation Item debe tener {fn} tras migrate")
			self.assertEqual(f.fieldtype, "Text Editor")
			self.assertTrue(f.hidden, f"{fn} debe estar oculto en Quotation Item")
			self.assertTrue(f.read_only, f"{fn} debe ser read_only en Quotation Item")

	def test_loader_manages_item_proposal_fields(self):
		"""El loader crea, actualiza y limpia (null explícito) los 3 campos de contenido en Item."""
		if not _migrated():
			self.skipTest("requiere bench migrate del rediseño")
		import os
		import tempfile

		from erpnext_proposals.erpnext_proposals.catalog_data import catalog_loader
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_item_group

		code = "_ITEMPROP-LOADER"
		grp = get_test_item_group()
		uom = "Nos" if frappe.db.exists("UOM", "Nos") else frappe.db.get_value("UOM", {}, "name")
		fd, path = tempfile.mkstemp(suffix=".json")
		os.close(fd)

		def _cat(vals):
			item = {
				"item_code": code,
				"item_name": "Loader Prop",
				"item_group": grp,
				"stock_uom": uom,
				"is_stock_item": 0,
			}
			item.update(vals)
			return {
				"version": "t",
				"catalog": "demo",
				"phases": [],
				"sections": [],
				"versioned": [],
				"items": [item],
				"scope_items": [],
				"templates": [],
			}

		try:
			with open(path, "w", encoding="utf-8") as fh:
				json.dump(_cat({f: f"<p>{f}</p>" for f in QITEM_TECH_FIELDS}), fh)
			catalog_loader.run(catalog_path=path, dry_run=False)
			for f in QITEM_TECH_FIELDS:
				self.assertEqual(frappe.db.get_value("Item", code, f), f"<p>{f}</p>")

			with open(path, "w", encoding="utf-8") as fh:
				json.dump(_cat({f: f"<p>{f} v2</p>" for f in QITEM_TECH_FIELDS}), fh)
			catalog_loader.run(catalog_path=path, dry_run=False, update_content=True)
			for f in QITEM_TECH_FIELDS:
				self.assertEqual(frappe.db.get_value("Item", code, f), f"<p>{f} v2</p>")

			with open(path, "w", encoding="utf-8") as fh:
				json.dump(_cat({f: None for f in QITEM_TECH_FIELDS}), fh)
			catalog_loader.run(catalog_path=path, dry_run=False, update_content=True)
			for f in QITEM_TECH_FIELDS:
				self.assertFalse(frappe.db.get_value("Item", code, f), f"{f} debe quedar vacío")
		finally:
			os.remove(path)
			if frappe.db.exists("Item", code):
				frappe.delete_doc("Item", code, force=True, ignore_permissions=True)
			frappe.db.commit()  # nosemgrep — limpieza de fixtures de test
