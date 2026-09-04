"""Tests del mecanismo genérico `clear_fields` del catalog_loader.

Cubre: vaciado efectivo de un Link existente, dry-run sin escritura, idempotencia, campo
inexistente/inválido, campo protegido y catálogo legacy sin `clear_fields`. Datos ficticios (`_TEST-`),
sin información de ningún cliente.
"""

import json
import tempfile
import unittest

import frappe

from erpnext_proposals.erpnext_proposals.catalog_data import catalog_loader

TPL = "_TEST-CLR Template"
PF = "_TEST-CLR PF"


def _run(cat: dict, dry_run: bool = False, **kw):
	fd, path = tempfile.mkstemp(suffix=".json")
	import os

	try:
		with open(path, "w", encoding="utf-8") as fh:
			json.dump(cat, fh, ensure_ascii=False)
		return catalog_loader.run(catalog_path=path, dry_run=dry_run, **kw)
	finally:
		os.close(fd)
		os.remove(path)


def _cat(clear_fields=None) -> dict:
	"""Catálogo mínimo con el template de prueba; opcionalmente declara `clear_fields`."""
	tpl = {"template_name": TPL, "sections": []}
	if clear_fields is not None:
		tpl["clear_fields"] = clear_fields
	return {
		"version": "test-clear",
		"phases": [],
		"sections": [],
		"scope_items": [],
		"templates": [tpl],
	}


class TestCatalogClearFields(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		if not frappe.db.exists("Print Format", PF):
			frappe.get_doc(
				{
					"doctype": "Print Format",
					"name": PF,
					"doc_type": "Quotation",
					"standard": "No",
					"print_format_type": "Jinja",
					"html": "<div>_TEST</div>",
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TPL):
			frappe.get_doc(
				{
					"doctype": "Proposal Template",
					"template_name": TPL,
					"description": "orig",
					"sow_print_format": PF,
				}
			).insert(ignore_permissions=True, ignore_mandatory=True)
		frappe.db.commit()  # nosemgrep — fixture de test

	@classmethod
	def tearDownClass(cls):
		if frappe.db.exists("Proposal Template", TPL):
			frappe.delete_doc("Proposal Template", TPL, force=True, ignore_permissions=True)
		if frappe.db.exists("Print Format", PF):
			frappe.delete_doc("Print Format", PF, force=True, ignore_permissions=True)
		frappe.db.commit()  # nosemgrep — limpieza de test

	def _set_sow(self, val):
		frappe.db.set_value("Proposal Template", TPL, "sow_print_format", val, update_modified=False)
		frappe.db.commit()  # nosemgrep — precondición de test

	def _sow(self):
		return frappe.db.get_value("Proposal Template", TPL, "sow_print_format")

	def _cleared_for_tpl(self, rep):
		return [u for u in rep.get("updated", []) if TPL in u and "clear_fields" in u]

	# 1) vaciado efectivo de un Link existente
	def test_1_clears_existing_link(self):
		self._set_sow(PF)
		rep = _run(_cat(clear_fields=["sow_print_format"]), dry_run=False, update_content=True)
		self.assertFalse(self._sow())  # None o ""
		self.assertTrue(self._cleared_for_tpl(rep), rep.get("updated"))

	# 2) dry-run: reporta updated pero NO escribe
	def test_2_dry_run_no_write(self):
		self._set_sow(PF)
		rep = _run(_cat(clear_fields=["sow_print_format"]), dry_run=True, update_content=True)
		self.assertEqual(self._sow(), PF)  # sin escritura
		self.assertTrue(self._cleared_for_tpl(rep))  # reportado igualmente

	# 3) idempotencia: segunda ejecución no reporta cambio
	def test_3_idempotent(self):
		self._set_sow(PF)
		_run(_cat(clear_fields=["sow_print_format"]), dry_run=False, update_content=True)
		self.assertFalse(self._sow())
		rep2 = _run(_cat(clear_fields=["sow_print_format"]), dry_run=False, update_content=True)
		self.assertFalse(self._sow())
		self.assertEqual(self._cleared_for_tpl(rep2), [])  # ya vacío → sin cambio

	# 4) campo inexistente → conflicto, sin crash ni cambios
	def test_4_invalid_field(self):
		self._set_sow(PF)
		rep = _run(_cat(clear_fields=["campo_que_no_existe"]), dry_run=False, update_content=True)
		self.assertEqual(self._sow(), PF)
		self.assertTrue(any(TPL in c and "inexistente" in c for c in rep.get("conflicts", [])))

	# 5) campo protegido (name) → conflicto, sin cambios
	def test_5_forbidden_field(self):
		rep = _run(_cat(clear_fields=["name"]), dry_run=False, update_content=True)
		self.assertTrue(frappe.db.exists("Proposal Template", TPL))
		self.assertTrue(any(TPL in c and "protegido" in c for c in rep.get("conflicts", [])))

	# 6) update_content=False → no vacía; lo reporta como conflicto pendiente
	def test_6_requires_update_content(self):
		self._set_sow(PF)
		rep = _run(_cat(clear_fields=["sow_print_format"]), dry_run=False, update_content=False)
		self.assertEqual(self._sow(), PF)
		self.assertTrue(any(TPL in c and "clear_fields" in c for c in rep.get("conflicts", [])))

	# 7) catálogo legacy SIN clear_fields → el campo omitido NO se toca
	def test_7_legacy_without_clear_fields(self):
		self._set_sow(PF)
		_run(_cat(), dry_run=False, update_content=True)
		self.assertEqual(self._sow(), PF)  # ausencia del campo != borrarlo
