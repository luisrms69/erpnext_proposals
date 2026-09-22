"""Tests del mecanismo genérico `clear_fields` del catalog_loader.

Cubre: vaciado efectivo de un campo editorial existente, dry-run sin escritura, idempotencia, campo
inexistente/inválido, campo protegido y catálogo legacy sin `clear_fields`. Se ejerce sobre un tipo
EDITORIAL vigente (Item), ya que tras la depuración `clear_fields` solo admite sections/items/
letter_heads (templates/scope_items/phases se administran en Desk). Datos ficticios (`_TEST-`), sin
información de ningún cliente.
"""

import json
import os
import tempfile
import unittest

import frappe

from erpnext_proposals.erpnext_proposals.catalog_data import catalog_loader
from erpnext_proposals.erpnext_proposals.tests.company import get_test_item_group

ITEM = "_TEST-CLR-ITEM"
EDITORIAL_FIELD = "proposal_methodology"
SEED = "<p>metodología de prueba</p>"


def _run(cat: dict, dry_run: bool = False, **kw):
	fd, path = tempfile.mkstemp(suffix=".json")
	try:
		with open(path, "w", encoding="utf-8") as fh:
			json.dump(cat, fh, ensure_ascii=False)
		return catalog_loader.run(catalog_path=path, dry_run=dry_run, **kw)
	finally:
		os.close(fd)
		os.remove(path)


def _cat(clear_fields=None) -> dict:
	"""Catálogo mínimo con el Item de prueba; opcionalmente declara `clear_fields`."""
	item = {"item_code": ITEM}
	if clear_fields is not None:
		item["clear_fields"] = clear_fields
	return {"version": "test-clear", "sections": [], "items": [item]}


class TestCatalogClearFields(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		if not _migrated():
			return
		if not frappe.db.exists("Item", ITEM):
			grp = get_test_item_group()
			uom = "Nos" if frappe.db.exists("UOM", "Nos") else frappe.db.get_value("UOM", {}, "name")
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": "Clear Fields Demo",
					"item_group": grp,
					"stock_uom": uom,
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
		frappe.db.commit()  # nosemgrep — fixture de test

	@classmethod
	def tearDownClass(cls):
		if frappe.db.exists("Item", ITEM):
			frappe.delete_doc("Item", ITEM, force=True, ignore_permissions=True)
		frappe.db.commit()  # nosemgrep — limpieza de test

	def setUp(self):
		if not _migrated():
			self.skipTest("requiere el custom field editorial en Item (bench migrate del rediseño)")

	def _set_field(self, val):
		frappe.db.set_value("Item", ITEM, EDITORIAL_FIELD, val, update_modified=False)
		frappe.db.commit()  # nosemgrep — precondición de test

	def _field(self):
		return frappe.db.get_value("Item", ITEM, EDITORIAL_FIELD)

	def _cleared_for_item(self, rep):
		return [u for u in rep.get("updated", []) if ITEM in u and "clear_fields" in u]

	# 1) vaciado efectivo de un campo editorial existente
	def test_1_clears_existing_field(self):
		self._set_field(SEED)
		rep = _run(_cat(clear_fields=[EDITORIAL_FIELD]), dry_run=False, update_content=True)
		self.assertFalse(self._field())  # None o ""
		self.assertTrue(self._cleared_for_item(rep), rep.get("updated"))

	# 2) dry-run: reporta updated pero NO escribe
	def test_2_dry_run_no_write(self):
		self._set_field(SEED)
		rep = _run(_cat(clear_fields=[EDITORIAL_FIELD]), dry_run=True, update_content=True)
		self.assertEqual(self._field(), SEED)  # sin escritura
		self.assertTrue(self._cleared_for_item(rep))  # reportado igualmente

	# 3) idempotencia: segunda ejecución no reporta cambio
	def test_3_idempotent(self):
		self._set_field(SEED)
		_run(_cat(clear_fields=[EDITORIAL_FIELD]), dry_run=False, update_content=True)
		self.assertFalse(self._field())
		rep2 = _run(_cat(clear_fields=[EDITORIAL_FIELD]), dry_run=False, update_content=True)
		self.assertFalse(self._field())
		self.assertEqual(self._cleared_for_item(rep2), [])  # ya vacío → sin cambio

	# 4) campo inexistente → conflicto, sin crash ni cambios
	def test_4_invalid_field(self):
		self._set_field(SEED)
		rep = _run(_cat(clear_fields=["campo_que_no_existe"]), dry_run=False, update_content=True)
		self.assertEqual(self._field(), SEED)
		self.assertTrue(any(ITEM in c and "inexistente" in c for c in rep.get("conflicts", [])))

	# 5) campo protegido (name) → conflicto, sin cambios
	def test_5_forbidden_field(self):
		rep = _run(_cat(clear_fields=["name"]), dry_run=False, update_content=True)
		self.assertTrue(frappe.db.exists("Item", ITEM))
		self.assertTrue(any(ITEM in c and "protegido" in c for c in rep.get("conflicts", [])))

	# 6) update_content=False → no vacía; lo reporta como conflicto pendiente
	def test_6_requires_update_content(self):
		self._set_field(SEED)
		rep = _run(_cat(clear_fields=[EDITORIAL_FIELD]), dry_run=False, update_content=False)
		self.assertEqual(self._field(), SEED)
		self.assertTrue(any(ITEM in c and "clear_fields" in c for c in rep.get("conflicts", [])))

	# 7) catálogo legacy SIN clear_fields → el campo omitido NO se toca
	def test_7_legacy_without_clear_fields(self):
		self._set_field(SEED)
		_run(_cat(), dry_run=False, update_content=True)
		self.assertEqual(self._field(), SEED)  # ausencia del campo != borrarlo


def _migrated():
	"""True si el custom field editorial en Item ya existe (rediseño migrado)."""
	return frappe.get_meta("Item").get_field(EDITORIAL_FIELD) is not None
