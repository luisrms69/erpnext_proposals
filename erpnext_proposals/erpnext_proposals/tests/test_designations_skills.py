"""Capacidad genérica del loader: Designations (erpnext) + Skills (hrms) + relación nativa
Designation.skills, idempotente y con gate HRMS.

Datos ficticios únicamente. No carga perfiles reales. No crea Activity Types, tarifas ni empleados.
La ausencia de HRMS se simula parcheando `_hrms_available` (NO se instala/desinstala HRMS).
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import frappe

from erpnext_proposals.erpnext_proposals.catalog_data import catalog_loader

SKILLS = ["_TSKILL_A", "_TSKILL_B", "_TSKILL_C"]
DESIGS = ["_TDESIG_X", "_TDESIG_Y"]


def _catalog(skills=None, designations=None, with_profile_keys=True):
	cat = {
		"version": "t",
		"catalog": "demo_profiles",
		"phases": [],
		"sections": [],
		"versioned": [],
		"scope_items": [],
		"templates": [],
	}
	if with_profile_keys:
		cat["skills"] = skills or []
		cat["designations"] = designations or []
	return cat


def _run(cat, dry_run=False, **kw):
	fd, path = tempfile.mkstemp(suffix=".json")
	try:
		with os.fdopen(fd, "w", encoding="utf-8") as fh:
			json.dump(cat, fh)
		return catalog_loader.run(catalog_path=path, dry_run=dry_run, **kw)
	finally:
		os.remove(path)


class TestDesignationsSkills(unittest.TestCase):
	def tearDown(self):
		for d in DESIGS:
			if frappe.db.exists("Designation", d):
				frappe.delete_doc("Designation", d, force=True, ignore_permissions=True)
		for s in SKILLS:
			if frappe.db.exists("Skill", s):
				frappe.delete_doc("Skill", s, force=True, ignore_permissions=True)
		frappe.db.commit()  # nosemgrep — limpieza de fixtures de test

	def _needs_hrms(self):
		if not catalog_loader._hrms_available():
			self.skipTest("HRMS/Skill/Designation.skills no disponible en este site")

	# 1
	def test_create_skill(self):
		self._needs_hrms()
		rep = _run(_catalog(skills=[{"skill_name": "_TSKILL_A", "description": "<p>d</p>"}]))
		self.assertTrue(frappe.db.exists("Skill", "_TSKILL_A"))
		self.assertTrue(any("_TSKILL_A" in c for c in rep["created"]))

	# 2
	def test_skill_existing_not_overwritten(self):
		self._needs_hrms()
		_run(_catalog(skills=[{"skill_name": "_TSKILL_A", "description": "orig"}]))
		rep = _run(_catalog(skills=[{"skill_name": "_TSKILL_A", "description": "CAMBIADO"}]))
		self.assertEqual(frappe.db.get_value("Skill", "_TSKILL_A", "description"), "orig")
		self.assertTrue(any("_TSKILL_A" in c for c in rep["conflicts"]))

	# 3
	def test_create_designation(self):
		rep = _run(_catalog(designations=[{"designation_name": "_TDESIG_X", "description": "<p>d</p>"}]))
		self.assertTrue(frappe.db.exists("Designation", "_TDESIG_X"))
		self.assertTrue(any("_TDESIG_X" in c for c in rep["created"]))

	# 4
	def test_designation_existing_not_overwritten(self):
		_run(_catalog(designations=[{"designation_name": "_TDESIG_X", "description": "orig"}]))
		rep = _run(_catalog(designations=[{"designation_name": "_TDESIG_X", "description": "CAMBIADO"}]))
		self.assertEqual(frappe.db.get_value("Designation", "_TDESIG_X", "description"), "orig")
		self.assertTrue(any("_TDESIG_X" in c for c in rep["conflicts"]))

	# 5
	def test_add_missing_skills_to_designation(self):
		self._needs_hrms()
		_run(
			_catalog(
				skills=[{"skill_name": s} for s in ("_TSKILL_A", "_TSKILL_B")],
				designations=[{"designation_name": "_TDESIG_X", "skills": ["_TSKILL_A", "_TSKILL_B"]}],
			)
		)
		rows = frappe.get_all("Designation Skill", filters={"parent": "_TDESIG_X"}, pluck="skill")
		self.assertEqual(sorted(rows), ["_TSKILL_A", "_TSKILL_B"])

	# 6
	def test_rerun_no_duplicates(self):
		self._needs_hrms()
		cat = _catalog(
			skills=[{"skill_name": s} for s in ("_TSKILL_A", "_TSKILL_B")],
			designations=[{"designation_name": "_TDESIG_X", "skills": ["_TSKILL_A", "_TSKILL_B"]}],
		)
		_run(cat)
		rep2 = _run(cat)
		self.assertEqual(len(rep2["created"]), 0)
		self.assertEqual(len(rep2["updated"]), 0)
		self.assertEqual(len(rep2["conflicts"]), 0)
		rows = frappe.get_all("Designation Skill", filters={"parent": "_TDESIG_X"}, pluck="skill")
		self.assertEqual(sorted(rows), ["_TSKILL_A", "_TSKILL_B"])

	# 7
	def test_preserve_extra_existing_skills(self):
		self._needs_hrms()
		_run(_catalog(skills=[{"skill_name": s} for s in SKILLS]))  # A, B, C
		# Designation con C agregada manualmente (fuera del catálogo).
		d = frappe.get_doc({"doctype": "Designation", "designation_name": "_TDESIG_X"})
		d.append("skills", {"skill": "_TSKILL_C"})
		d.insert(ignore_permissions=True)
		# El catálogo agrega A y B (no menciona C).
		_run(_catalog(designations=[{"designation_name": "_TDESIG_X", "skills": ["_TSKILL_A", "_TSKILL_B"]}]))
		rows = frappe.get_all("Designation Skill", filters={"parent": "_TDESIG_X"}, pluck="skill")
		self.assertEqual(sorted(rows), ["_TSKILL_A", "_TSKILL_B", "_TSKILL_C"])  # C conservada

	# 8
	def test_hrms_absent_designation_created_skills_pending(self):
		with patch.object(catalog_loader, "_hrms_available", return_value=False):
			rep = _run(
				_catalog(
					skills=[{"skill_name": "_TSKILL_A"}],
					designations=[{"designation_name": "_TDESIG_X", "skills": ["_TSKILL_A"]}],
				)
			)
		self.assertTrue(frappe.db.exists("Designation", "_TDESIG_X"))  # Designation sí se crea
		self.assertFalse(frappe.db.exists("Skill", "_TSKILL_A"))  # Skill NO (sin HRMS)
		self.assertTrue(any("_TSKILL_A" in p for p in rep["pending"]))
		self.assertTrue(any("_TDESIG_X" in p and "pendiente" in p for p in rep["pending"]))

	# 9
	def test_later_run_completes_pending(self):
		self._needs_hrms()  # el completado requiere HRMS realmente presente
		with patch.object(catalog_loader, "_hrms_available", return_value=False):
			_run(
				_catalog(
					skills=[{"skill_name": "_TSKILL_A"}],
					designations=[{"designation_name": "_TDESIG_X", "skills": ["_TSKILL_A"]}],
				)
			)
		self.assertFalse(frappe.db.exists("Skill", "_TSKILL_A"))
		# Reejecución con HRMS presente completa Skill + relación.
		_run(
			_catalog(
				skills=[{"skill_name": "_TSKILL_A"}],
				designations=[{"designation_name": "_TDESIG_X", "skills": ["_TSKILL_A"]}],
			)
		)
		self.assertTrue(frappe.db.exists("Skill", "_TSKILL_A"))
		rows = frappe.get_all("Designation Skill", filters={"parent": "_TDESIG_X"}, pluck="skill")
		self.assertIn("_TSKILL_A", rows)

	# 10
	def test_dry_run_no_write(self):
		self._needs_hrms()
		rep = _run(
			_catalog(
				skills=[{"skill_name": "_TSKILL_A"}],
				designations=[{"designation_name": "_TDESIG_X", "skills": ["_TSKILL_A"]}],
			),
			dry_run=True,
		)
		self.assertFalse(frappe.db.exists("Skill", "_TSKILL_A"))
		self.assertFalse(frappe.db.exists("Designation", "_TDESIG_X"))
		self.assertTrue(rep["created"])  # el plan reporta lo que crearía

	# 11
	def test_reports_differences(self):
		self._needs_hrms()
		_run(_catalog(skills=[{"skill_name": "_TSKILL_A", "description": "orig"}]))
		rep = _run(_catalog(skills=[{"skill_name": "_TSKILL_A", "description": "nuevo"}]))
		self.assertTrue(any("_TSKILL_A" in c and "description" in c for c in rep["conflicts"]))

	# 12
	def test_catalog_without_profile_sections(self):
		rep = _run(_catalog(with_profile_keys=False))  # catálogo legacy sin skills ni designations
		self.assertEqual(len(rep["conflicts"]), 0)
		self.assertFalse(any("Skill '" in c or "Designation '" in c for c in rep["created"]))
