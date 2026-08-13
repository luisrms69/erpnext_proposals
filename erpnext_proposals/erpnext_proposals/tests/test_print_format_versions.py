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

	# A.2 — el versionador es dueño exclusivo de `disabled` de un formato sustituido: `_seed_print_formats`
	#        NO lo gestiona (aunque el catálogo lo declare distinto) → sin flip-flop → idempotente.
	def test_a2_versioner_owns_disabled_of_superseded(self):
		from erpnext_proposals.erpnext_proposals.catalog_data.catalog_loader import _seed_print_formats

		# OLD ya deshabilitado en el site (estado tras versionar); el catálogo lo declara disabled=0.
		frappe.db.set_value("Print Format", OLD, "disabled", 1)
		spec = {
			"name": OLD,
			"doc_type": "Quotation",
			"print_format_type": "Jinja",
			"standard": "No",
			"custom_format": 1,
			"disabled": 0,
			"html": "<p>x</p>",
		}

		def _run_seed(superseded):
			rep = {
				"created": [],
				"reused": [],
				"updated": [],
				"unchanged": [],
				"conflicts": [],
				"pending": [],
			}
			_seed_print_formats(
				[spec], self._tmp, rep, dry_run=True, update_content=True, superseded=superseded
			)
			return rep

		# CONTROL: sin `superseded`, `disabled` (1 vs 0) sí saldría como actualización.
		ctrl = _run_seed(set())
		self.assertTrue(
			any("disabled" in u for u in ctrl["updated"]), "control: sin superseded debería tocar disabled"
		)

		# Con OLD en `superseded`: `disabled` NO se gestiona → sin cambios.
		rep = _run_seed({OLD})
		self.assertNotIn("disabled", " ".join(rep["updated"]))
		self.assertIn(f"Print Format '{OLD}'", " ".join(rep["unchanged"]))
		self.assertEqual(rep["conflicts"], [])

	# B — cambiar la presentación (html/css/…) de un formato HISTÓRICO se reporta como CONFLICT desde el
	#     dry-run (antes de que ADR-0011 reviente en el save del apply). `disabled` NO cae en este guard.
	def test_b_historical_content_change_is_conflict(self):
		from unittest.mock import patch

		from erpnext_proposals.erpnext_proposals.catalog_data import catalog_loader as L

		spec = {
			"name": OLD,  # en el site tiene html "<p>x</p>"
			"doc_type": "Quotation",
			"print_format_type": "Jinja",
			"standard": "No",
			"custom_format": 1,
			"disabled": 0,
			"html": "<p>CONTENIDO CAMBIADO</p>",
		}
		rep = {"created": [], "reused": [], "updated": [], "unchanged": [], "conflicts": [], "pending": []}
		with patch(
			"erpnext_proposals.erpnext_proposals.utils.print_format_protection.is_print_format_historical",
			return_value=True,
		):
			L._seed_print_formats([spec], self._tmp, rep, dry_run=True, update_content=True)
		self.assertTrue(any("HISTÓRICO" in c for c in rep["conflicts"]), rep["conflicts"])
		self.assertEqual(rep["updated"], [], "no debe contarse como actualización")

	def assertNoConflicts(self, report):
		self.assertEqual(report["conflicts"], [], f"no debe haber conflictos: {report['conflicts']}")
