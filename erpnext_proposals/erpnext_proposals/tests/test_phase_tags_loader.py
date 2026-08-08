"""Loader: Tags nativos de catálogo → Proposal Phase (capacidad v7 `phase_tags`).

Verifica que el loader materialice, mediante el mecanismo NATIVO de Frappe (DocTags), los Tags
declarados por línea en el catálogo sobre su Proposal Phase, de forma genérica, idempotente y NO
destructiva (preserva Tags ajenos). El split de `area_tags` por comas es responsabilidad del
normalizer; el loader recibe la lista final.

Datos ficticios; nunca contenido de cliente. Nombres de Tags y códigos de fase locales al test.
"""

import json
import os
import tempfile
import unittest

import frappe
from frappe.desk.doctype.tag.tag import DocTags

from erpnext_proposals.erpnext_proposals.catalog_data import catalog_loader

PHASE = "_TAGL_P1"
TAGS = ["_TagSvc", "_TagAreaA", "_TagAreaB"]  # servicio + varias áreas (ya split)


def _tag_links(dt, dn):
	return set(frappe.get_all("Tag Link", filters={"document_type": dt, "document_name": dn}, pluck="tag"))


def _catalog(tags):
	return {
		"version": "t",
		"catalog": "phase_tags_demo",
		"phases": [{"phase_code": PHASE, "phase_name": "Fase tags loader", "sequence": 10, "tags": tags}],
		"sections": [],
		"versioned": [],
		"scope_items": [],
		"templates": [],
	}


def _run(cat, dry_run=False):
	fd, path = tempfile.mkstemp(suffix=".json")
	try:
		with os.fdopen(fd, "w", encoding="utf-8") as fh:
			json.dump(cat, fh)
		return catalog_loader.run(catalog_path=path, dry_run=dry_run)
	finally:
		os.remove(path)


class TestPhaseTagsLoader(unittest.TestCase):
	def tearDown(self):
		if frappe.db.exists("Proposal Phase", PHASE):
			frappe.delete_doc("Proposal Phase", PHASE, force=True, ignore_permissions=True)
		for t in [*TAGS, "_TagAjeno"]:
			if frappe.db.exists("Tag", t):
				frappe.delete_doc("Tag", t, force=True, ignore_permissions=True)
		frappe.db.commit()  # nosemgrep — limpieza de fixtures de test

	def test_capability_present(self):
		caps = catalog_loader.capabilities()
		self.assertGreaterEqual(caps["caps_version"], 7)
		self.assertTrue(caps["phase_tags"])

	def test_phase_gets_native_tags(self):
		_run(_catalog(TAGS))
		self.assertTrue(frappe.db.exists("Proposal Phase", PHASE))
		self.assertEqual(_tag_links("Proposal Phase", PHASE), set(TAGS))

	def test_idempotent_rerun(self):
		_run(_catalog(TAGS))
		rep = _run(_catalog(TAGS))
		self.assertEqual(_tag_links("Proposal Phase", PHASE), set(TAGS))
		# Segunda corrida: nada nuevo que agregar (no aparece en updated por tags).
		self.assertFalse(any(PHASE in u and "tags" in u for u in rep["updated"]))

	def test_non_destructive_preserves_foreign_tags(self):
		_run(_catalog(TAGS[:1]))  # crea la fase con un tag del catálogo
		DocTags("Proposal Phase").add(PHASE, "_TagAjeno")  # tag ajeno (no administrado por catálogo)
		_run(_catalog(TAGS))  # el catálogo agrega el resto; NO debe borrar el ajeno
		self.assertEqual(_tag_links("Proposal Phase", PHASE), set(TAGS) | {"_TagAjeno"})

	def test_dry_run_no_write(self):
		rep = _run(_catalog(TAGS), dry_run=True)
		self.assertFalse(frappe.db.exists("Proposal Phase", PHASE))
		self.assertTrue(any(PHASE in u and "tags" in u for u in rep["updated"]))
