"""Loader del catálogo con planeación PMO y dependencias, más la validación del grafo de
dependencias del Scope Item.

Cubre: importación de Scope Items sin el Item comercial existente (erpnext_item pendiente),
vinculación automática al re-ejecutar tras crear el Item, siembra idempotente de dependencias
(depends_on, segundo paso), dependencia a un Scope Item inexistente (omitida), y las validaciones
de auto-referencia, duplicado y ciclo del Scope Item.

Datos ficticios; nunca contenido de cliente.
"""

import json
import os
import tempfile
import unittest

import frappe
from frappe.exceptions import ValidationError

from erpnext_proposals.erpnext_proposals.catalog_data import catalog_loader

PHASE = "_SCPMO_PHASE"
ITEM = "_SCPMO_ITEM"
SCOPES = ["_SCPMO_A", "_SCPMO_B", "_SCPMO_C"]


def _write(cat) -> str:
	fd, path = tempfile.mkstemp(suffix=".json")
	with os.fdopen(fd, "w", encoding="utf-8") as fh:
		json.dump(cat, fh)
	return path


class TestScopePmoCatalog(unittest.TestCase):
	def tearDown(self):
		for c in [*SCOPES, "_SCPMO_SELF", "_SCPMO_X", "_SCPMO_Y"]:
			if frappe.db.exists("Scope Item", c):
				frappe.delete_doc("Scope Item", c, force=True, ignore_permissions=True)
		if frappe.db.exists("Item", ITEM):
			frappe.delete_doc("Item", ITEM, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Phase", PHASE):
			frappe.delete_doc("Proposal Phase", PHASE, force=True, ignore_permissions=True)
		frappe.db.commit()  # nosemgrep — limpieza de fixtures de test

	def _base_catalog(self, with_item: bool):
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_item_group

		grp = get_test_item_group()
		uom = "Nos" if frappe.db.exists("UOM", "Nos") else frappe.db.get_value("UOM", {}, "name")
		items = []
		if with_item:
			items = [
				{
					"item_code": ITEM,
					"item_name": "SCPMO Item",
					"item_group": grp,
					"stock_uom": uom,
					"is_stock_item": 0,
					"is_sales_item": 1,
				}
			]
		return {
			"version": "t",
			"catalog": "scpmo",
			"phases": [{"phase_code": PHASE, "phase_name": "SCPMO", "sequence": 5}],
			"sections": [],
			"versioned": [],
			"items": items,
			"scope_items": [
				{
					"code": "_SCPMO_A",
					"title": "A",
					"sequence": 10,
					"phase": PHASE,
					"erpnext_item": ITEM,
					"planned_start_offset_days": 0,
					"planned_duration_days": 2,
					"is_milestone": 0,
				},
				{
					"code": "_SCPMO_B",
					"title": "B",
					"sequence": 20,
					"phase": PHASE,
					"erpnext_item": ITEM,
					"planned_start_offset_days": -3,
					"planned_duration_days": 1,
					"is_milestone": 1,
					"depends_on": ["_SCPMO_A"],
				},
			],
			"templates": [],
		}

	# ── Scope Items sin Item comercial existente → erpnext_item pendiente ──

	def test_scope_created_without_item_then_linked_on_rerun(self):
		# 1) Item NO existe: los Scope Items se crean, erpnext_item queda pendiente.
		path = _write(self._base_catalog(with_item=False))
		try:
			rep = catalog_loader.run(catalog_path=path, dry_run=False)
			self.assertTrue(frappe.db.exists("Scope Item", "_SCPMO_A"))
			self.assertFalse(frappe.db.get_value("Scope Item", "_SCPMO_A", "erpnext_item"))
			self.assertTrue(any("_SCPMO_A" in p and "pendiente" in p for p in rep["pending"]))
			# La planeación PMO sí se cargó.
			self.assertEqual(frappe.db.get_value("Scope Item", "_SCPMO_A", "planned_duration_days"), 2)
			self.assertEqual(int(frappe.db.get_value("Scope Item", "_SCPMO_B", "is_milestone")), 1)
		finally:
			os.remove(path)

		# 2) Ahora el catálogo incluye el Item: re-ejecutar completa el Link sin duplicar Scope Items.
		path2 = _write(self._base_catalog(with_item=True))
		try:
			rep2 = catalog_loader.run(catalog_path=path2, dry_run=False, update_content=True)
			self.assertEqual(frappe.db.get_value("Scope Item", "_SCPMO_A", "erpnext_item"), ITEM)
			self.assertEqual(frappe.db.count("Scope Item", {"code": "_SCPMO_A"}), 1)
			self.assertFalse(any("_SCPMO_A" in p and "pendiente" in p for p in rep2.get("pending", [])))
		finally:
			os.remove(path2)

	# ── Siembra idempotente de dependencias (segundo paso) ──

	def test_dependency_seeding_idempotent(self):
		path = _write(self._base_catalog(with_item=True))
		try:
			catalog_loader.run(catalog_path=path, dry_run=False)
			deps = frappe.get_all(
				"Scope Item Dependency",
				filters={"parent": "_SCPMO_B", "parenttype": "Scope Item"},
				pluck="depends_on",
			)
			self.assertEqual(deps, ["_SCPMO_A"])
			# Reejecutar es idempotente: sin updates ni conflictos por dependencias.
			rep2 = catalog_loader.run(catalog_path=path, dry_run=False)
			self.assertEqual(len(rep2["updated"]), 0)
			self.assertEqual(len(rep2["conflicts"]), 0)
		finally:
			os.remove(path)

	def test_dependency_to_missing_scope_is_skipped(self):
		cat = self._base_catalog(with_item=True)
		# B depende de un Scope Item que no está en el catálogo.
		cat["scope_items"][1]["depends_on"] = ["_SCPMO_A", "_SCPMO_GHOST"]
		path = _write(cat)
		try:
			rep = catalog_loader.run(catalog_path=path, dry_run=False)
			deps = frappe.get_all(
				"Scope Item Dependency",
				filters={"parent": "_SCPMO_B", "parenttype": "Scope Item"},
				pluck="depends_on",
			)
			self.assertEqual(deps, ["_SCPMO_A"], "La dependencia inexistente se omite, no rompe el Link")
			self.assertTrue(any("_SCPMO_GHOST" in p for p in rep["pending"]))
		finally:
			os.remove(path)

	# ── Validación del grafo de dependencias del Scope Item ──

	def test_self_dependency_rejected(self):
		frappe.get_doc(
			{"doctype": "Scope Item", "code": "_SCPMO_SELF", "title": "Self", "sequence": 1, "enabled": 1}
		).insert(ignore_permissions=True)
		doc = frappe.get_doc("Scope Item", "_SCPMO_SELF")
		doc.append("depends_on_scope_items", {"depends_on": "_SCPMO_SELF"})
		with self.assertRaises(ValidationError):
			doc.save(ignore_permissions=True)

	def test_duplicate_dependency_rejected(self):
		frappe.get_doc(
			{"doctype": "Scope Item", "code": "_SCPMO_X", "title": "X", "sequence": 1, "enabled": 1}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{"doctype": "Scope Item", "code": "_SCPMO_Y", "title": "Y", "sequence": 2, "enabled": 1}
		).insert(ignore_permissions=True)
		doc = frappe.get_doc("Scope Item", "_SCPMO_Y")
		doc.append("depends_on_scope_items", {"depends_on": "_SCPMO_X"})
		doc.append("depends_on_scope_items", {"depends_on": "_SCPMO_X"})
		with self.assertRaises(ValidationError):
			doc.save(ignore_permissions=True)

	def test_cycle_rejected(self):
		# A depende de B; luego B depende de A → ciclo.
		frappe.get_doc(
			{"doctype": "Scope Item", "code": "_SCPMO_X", "title": "X", "sequence": 1, "enabled": 1}
		).insert(ignore_permissions=True)
		b = frappe.get_doc(
			{"doctype": "Scope Item", "code": "_SCPMO_Y", "title": "Y", "sequence": 2, "enabled": 1}
		)
		b.insert(ignore_permissions=True)
		a = frappe.get_doc("Scope Item", "_SCPMO_X")
		a.append("depends_on_scope_items", {"depends_on": "_SCPMO_Y"})
		a.save(ignore_permissions=True)
		b = frappe.get_doc("Scope Item", "_SCPMO_Y")
		b.append("depends_on_scope_items", {"depends_on": "_SCPMO_X"})
		with self.assertRaises(ValidationError):
			b.save(ignore_permissions=True)
