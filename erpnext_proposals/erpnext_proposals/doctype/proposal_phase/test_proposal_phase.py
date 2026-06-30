# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Pruebas del catálogo Proposal Phase.

Foco: la INMUTABILIDAD de `phase_code` por todas las vías razonables (save, reload,
db_set vía documento, rename), y que el resto de campos (`phase_name`, `sequence`,
`enabled`) sí sean editables. No depende de Company ni Fiscal Year.
"""

import unittest

import frappe


class TestProposalPhase(unittest.TestCase):
	PREFIX = "_TEST_PH_"

	def tearDown(self):
		frappe.db.rollback()
		for name in frappe.get_all(
			"Proposal Phase", filters={"phase_code": ["like", f"{self.PREFIX}%"]}, pluck="name"
		):
			frappe.delete_doc("Proposal Phase", name, force=True, ignore_permissions=True)
		frappe.db.commit()  # nosemgrep — test cleanup

	def _make(self, code, name="Fase", seq=10):
		return frappe.get_doc(
			{
				"doctype": "Proposal Phase",
				"phase_code": f"{self.PREFIX}{code}",
				"phase_name": name,
				"sequence": seq,
			}
		).insert(ignore_permissions=True)

	# ── Creación / naming / defaults ────────────────────────────────────────

	def test_autoname_equals_phase_code(self):
		doc = self._make("ANALISIS", "Análisis", 10)
		self.assertEqual(doc.name, f"{self.PREFIX}ANALISIS")

	def test_enabled_defaults_to_one(self):
		doc = self._make("DEFAULTS", "Defaults", 10)
		self.assertEqual(doc.enabled, 1)

	# ── Inmutabilidad de phase_code ─────────────────────────────────────────

	def test_phase_code_immutable_same_instance(self):
		doc = self._make("IMM1", "Inmutable 1", 10)
		doc.phase_code = f"{self.PREFIX}IMM1_X"
		with self.assertRaises(frappe.exceptions.CannotChangeConstantError):
			doc.save(ignore_permissions=True)

	def test_phase_code_immutable_after_reload(self):
		doc = self._make("IMM2", "Inmutable 2", 10)
		fresh = frappe.get_doc("Proposal Phase", doc.name)
		fresh.phase_code = f"{self.PREFIX}IMM2_X"
		with self.assertRaises(frappe.exceptions.CannotChangeConstantError):
			fresh.save(ignore_permissions=True)

	def test_phase_code_immutable_via_db_set_on_document(self):
		# db_set sobre el documento (no el raw frappe.db.set_value) debe respetar set_only_once
		doc = self._make("IMM3", "Inmutable 3", 10)
		with self.assertRaises(frappe.exceptions.CannotChangeConstantError):
			doc.set("phase_code", f"{self.PREFIX}IMM3_X")
			doc.save(ignore_permissions=True)

	def test_rename_is_blocked(self):
		doc = self._make("RENAME", "No renombrable", 10)
		with self.assertRaises(Exception):
			frappe.rename_doc("Proposal Phase", doc.name, f"{self.PREFIX}RENAME_NEW", force=True)
		# El name original sigue existiendo intacto
		self.assertTrue(frappe.db.exists("Proposal Phase", doc.name))

	def test_name_stable_after_phase_name_change(self):
		doc = self._make("STABLE", "Original", 10)
		original_name = doc.name
		doc.phase_name = "Cambiado"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.name, original_name)
		self.assertTrue(frappe.db.exists("Proposal Phase", original_name))

	# ── Campos editables ────────────────────────────────────────────────────

	def test_phase_name_is_editable(self):
		doc = self._make("EDIT_NAME", "Implementación", 30)
		doc.phase_name = "Despliegue"
		doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Proposal Phase", doc.name, "phase_name"), "Despliegue")

	def test_sequence_is_editable_and_not_unique(self):
		a = self._make("SEQ_A", "A", 50)
		b = self._make("SEQ_B", "B", 50)  # misma secuencia permitida
		self.assertEqual(a.sequence, 50)
		self.assertEqual(b.sequence, 50)
		a.sequence = 99
		a.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Proposal Phase", a.name, "sequence"), 99)

	def test_enabled_is_editable(self):
		doc = self._make("TOGGLE", "Toggle", 10)
		doc.enabled = 0
		doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Proposal Phase", doc.name, "enabled"), 0)

	# ── Validaciones de catálogo ────────────────────────────────────────────

	def test_phase_code_required(self):
		# Sin phase_code, el autoname (field:phase_code) lanza ValidationError ("is required")
		# antes de la validación de mandatory. MandatoryError es subclase de ValidationError.
		with self.assertRaises(frappe.exceptions.ValidationError):
			frappe.get_doc({"doctype": "Proposal Phase", "phase_name": "Sin código", "sequence": 10}).insert(
				ignore_permissions=True
			)

	def test_phase_name_required(self):
		with self.assertRaises(frappe.exceptions.MandatoryError):
			frappe.get_doc(
				{"doctype": "Proposal Phase", "phase_code": f"{self.PREFIX}NONAME", "sequence": 10}
			).insert(ignore_permissions=True)

	def test_phase_code_unique(self):
		self._make("DUP", "Uno", 10)
		with self.assertRaises(frappe.exceptions.DuplicateEntryError):
			self._make("DUP", "Dos", 20)
