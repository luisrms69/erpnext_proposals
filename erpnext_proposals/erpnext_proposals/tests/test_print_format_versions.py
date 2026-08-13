"""Versionamiento genérico de Print Formats en el loader (`_seed_print_format_versions`).

Demuestra el ciclo declarativo e IDEMPOTENTE: crear formato nuevo (ya existe) → deshabilitar el
anterior → adjuntar changelog (File) → repuntar Proposal Templates. Segunda aplicación: sin cambios
efectivos (no duplica File, no re-deshabilita, no re-repunta). Datos ficticios.
"""

import os
import shutil
import tempfile
import unittest

import frappe

from erpnext_proposals.erpnext_proposals.catalog_data.catalog_loader import _seed_print_format_versions

OLD = "_Test PFV Anterior"
NEW = "_Test PFV — 2026-08-12 — V1"
TMPL = "_Test PFV Template"


def _mkpf(name, disabled=0):
	if frappe.db.exists("Print Format", name):
		return
	frappe.get_doc(
		{
			"doctype": "Print Format",
			"name": name,
			"doc_type": "Quotation",
			"standard": "No",
			"custom_format": 1,
			"print_format_type": "Jinja",
			"disabled": disabled,
			"html": "<p>x</p>",
		}
	).insert(ignore_permissions=True)


class TestPrintFormatVersions(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._tmp = tempfile.mkdtemp()
		os.makedirs(os.path.join(cls._tmp, "changelogs"), exist_ok=True)
		with open(os.path.join(cls._tmp, "changelogs", "cl.md"), "w", encoding="utf-8") as fh:
			fh.write("# changelog de prueba\n")

	@classmethod
	def tearDownClass(cls):
		cls._purge()
		shutil.rmtree(cls._tmp, ignore_errors=True)
		super().tearDownClass()

	@classmethod
	def _purge(cls):
		for fn in frappe.get_all(
			"File", filters={"attached_to_doctype": "Print Format", "attached_to_name": NEW}, pluck="name"
		):
			frappe.delete_doc("File", fn, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TMPL):
			frappe.delete_doc("Proposal Template", TMPL, force=True, ignore_permissions=True)
		for n in (OLD, NEW):
			if frappe.db.exists("Print Format", n):
				frappe.delete_doc("Print Format", n, force=True, ignore_permissions=True)
		frappe.db.commit()

	def setUp(self):
		self._purge()
		_mkpf(OLD, 0)
		_mkpf(NEW, 0)
		frappe.get_doc({"doctype": "Proposal Template", "template_name": TMPL, "print_format": OLD}).insert(
			ignore_permissions=True
		)

	def tearDown(self):
		self._purge()

	def _run(self):
		entry = {
			"current": NEW,
			"supersedes": OLD,
			"disable_superseded": True,
			"changelog_file": "changelogs/cl.md",
			"templates": [TMPL],
		}
		report = {"created": [], "reused": [], "updated": [], "unchanged": [], "conflicts": [], "pending": []}
		_seed_print_format_versions([entry], self._tmp, report, dry_run=False)
		frappe.db.commit()
		return report

	def _changelog_files(self):
		return frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "Print Format",
				"attached_to_name": NEW,
				"file_name": ["like", "cl%"],
			},
			pluck="name",
		)

	def test_first_apply_then_idempotent(self):
		# ── Primera aplicación ──
		r1 = self._run()
		self.assertEqual(
			frappe.db.get_value("Print Format", OLD, "disabled"), 1, "el anterior debe quedar disabled"
		)
		self.assertEqual(len(self._changelog_files()), 1, "changelog adjunto una vez")
		self.assertEqual(
			frappe.db.get_value("Proposal Template", TMPL, "print_format"), NEW, "template repuntado al nuevo"
		)
		self.assertTrue(any("disabled=1" in x for x in r1["updated"]))
		self.assertTrue(any("changelog" in x for x in r1["created"]))
		self.assertNoConflicts(r1)

		# ── Segunda aplicación: idempotente (sin cambios efectivos) ──
		r2 = self._run()
		self.assertEqual(len(self._changelog_files()), 1, "no duplica el File del changelog")
		self.assertEqual(frappe.db.get_value("Print Format", OLD, "disabled"), 1)
		self.assertEqual(frappe.db.get_value("Proposal Template", TMPL, "print_format"), NEW)
		self.assertEqual(r2["created"], [], "segunda corrida no crea nada")
		self.assertEqual(r2["updated"], [], "segunda corrida no actualiza nada")
		self.assertGreaterEqual(len(r2["unchanged"]), 3, "disable + changelog + repunte reportan unchanged")
		self.assertNoConflicts(r2)

	def test_current_missing_is_conflict_not_crash(self):
		# Si el formato vigente no existe (no declarado en print_formats), se reporta conflicto sin romper.
		frappe.delete_doc("Print Format", NEW, force=True, ignore_permissions=True)
		r = self._run()
		self.assertTrue(any("no existe" in c for c in r["conflicts"]))
		# el anterior NO se deshabilita si el vigente no existe
		self.assertEqual(frappe.db.get_value("Print Format", OLD, "disabled"), 0)

	def assertNoConflicts(self, report):
		self.assertEqual(report["conflicts"], [], f"no debe haber conflictos: {report['conflicts']}")
