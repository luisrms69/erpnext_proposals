"""Tests del loader genérico de catálogos (catalog_loader) con el catálogo de ejemplo ficticio.

Tras la depuración de fuentes de verdad (caps v12), el loader solo administra la capa editorial/de
presentación: Sections, contenido editorial de Item (sin crear Items), Letter Heads, Print Formats +
versionamiento y clear_fields. Cubre: dry_run sin escrituras, carga real, idempotencia, update_content,
conflictos, que las Sections base no se creen/modifiquen, contenido editorial de Item (nunca crea
Items), Print Formats y los límites de la allowlist. No usa datos de ningún cliente.
"""

import json
import unittest

import frappe

from erpnext_proposals.erpnext_proposals.catalog_data import catalog_loader

DEMO_SECTIONS = ["Presentación Demo", "Alcance Demo"]


def _sample() -> dict:
	with open(catalog_loader.SAMPLE_CATALOG, encoding="utf-8") as fh:
		return json.load(fh)


def _cleanup() -> None:
	for s in DEMO_SECTIONS:
		if frappe.db.exists("Proposal Section", s):
			frappe.delete_doc("Proposal Section", s, force=True, ignore_permissions=True)
	frappe.db.commit()  # nosemgrep — limpieza de fixtures de test


class TestCatalogLoader(unittest.TestCase):
	def tearDown(self):
		_cleanup()

	def test_dry_run_no_escribe(self):
		rep = catalog_loader.run(dry_run=True)
		self.assertTrue(rep["created"], "dry-run debe reportar registros por crear")
		self.assertFalse(frappe.db.exists("Proposal Section", "Presentación Demo"))

	def test_carga_real_e_idempotencia(self):
		catalog_loader.run(dry_run=False)
		self.assertTrue(frappe.db.exists("Proposal Section", "Presentación Demo"))
		self.assertTrue(frappe.db.exists("Proposal Section", "Alcance Demo"))
		# 2a corrida → idempotente
		rep2 = catalog_loader.run(dry_run=False)
		self.assertEqual(len(rep2["created"]), 0)
		self.assertEqual(len(rep2["updated"]), 0)
		self.assertEqual(len(rep2["conflicts"]), 0)

	def test_conflicto_sin_update_content(self):
		catalog_loader.run(dry_run=False)
		frappe.db.set_value("Proposal Section", "Presentación Demo", "content", "<p>modificado</p>")
		rep = catalog_loader.run(dry_run=False, update_content=False)
		self.assertTrue(any("Presentación Demo" in c for c in rep["conflicts"]))
		self.assertEqual(
			frappe.db.get_value("Proposal Section", "Presentación Demo", "content"), "<p>modificado</p>"
		)

	def test_update_content_restaura(self):
		catalog_loader.run(dry_run=False)
		frappe.db.set_value("Proposal Section", "Presentación Demo", "content", "<p>modificado</p>")
		rep = catalog_loader.run(dry_run=False, update_content=True)
		self.assertTrue(any("Presentación Demo" in u for u in rep["updated"]))
		self.assertIn(
			"{{ doc.customer_name }}",
			frappe.db.get_value("Proposal Section", "Presentación Demo", "content"),
		)

	def test_no_crea_sections_base(self):
		# el catálogo de ejemplo no incluye ninguna de las 10 Sections base
		nombres = {s["section_name"] for s in _sample()["sections"]}
		self.assertFalse(nombres & catalog_loader.BASE_SECTIONS)

	def test_item_editorial_content_managed_nunca_crea(self):
		"""El loader administra SOLO el contenido editorial de un Item que YA existe; nunca crea Items.
		Crea → update_content → null explícito. Un Item inexistente se reporta como pendiente y NO se crea.
		Datos ficticios."""
		import os
		import tempfile

		from erpnext_proposals.erpnext_proposals.tests.company import get_test_item_group

		code, ausente = "_DEMO-EDIT-ITEM", "_DEMO-EDIT-AUSENTE"
		fields = ("proposal_methodology", "proposal_expected_result", "proposal_scope_limit")
		grp = get_test_item_group()
		uom = "Nos" if frappe.db.exists("UOM", "Nos") else frappe.db.get_value("UOM", {}, "name")
		fd, path = tempfile.mkstemp(suffix=".json")
		os.close(fd)

		# El Item lo administra Desk: lo creamos nosotros (no el loader).
		if not frappe.db.exists("Item", code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": "Editorial Demo",
					"item_group": grp,
					"stock_uom": uom,
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
			frappe.db.commit()  # nosemgrep — fixture de test

		def _cat(item_code, vals):
			item = {"item_code": item_code}
			item.update(vals)
			return {"version": "t", "catalog": "demo_edit", "sections": [], "versioned": [], "items": [item]}

		def _run(item_code, vals, **kw):
			with open(path, "w", encoding="utf-8") as fh:
				json.dump(_cat(item_code, vals), fh)
			return catalog_loader.run(catalog_path=path, **kw)

		try:
			# 1) fija contenido editorial en el Item existente (requiere update_content: el Item ya existe)
			_run(code, {f: f"<p>{f}</p>" for f in fields}, dry_run=False, update_content=True)
			for f in fields:
				self.assertEqual(frappe.db.get_value("Item", code, f), f"<p>{f}</p>")

			# 2) update_content actualiza
			_run(code, {f: f"<p>{f} v2</p>" for f in fields}, dry_run=False, update_content=True)
			for f in fields:
				self.assertEqual(frappe.db.get_value("Item", code, f), f"<p>{f} v2</p>")

			# 3) null explícito limpia
			_run(code, {f: None for f in fields}, dry_run=False, update_content=True)
			for f in fields:
				self.assertFalse(frappe.db.get_value("Item", code, f), f"{f} debe quedar vacío")

			# 4) Item inexistente → pendiente; el loader NO lo crea
			rep = _run(ausente, {"proposal_methodology": "<p>x</p>"}, dry_run=False)
			self.assertFalse(frappe.db.exists("Item", ausente), "el loader NUNCA crea Items")
			self.assertTrue(any(ausente in p for p in rep["pending"]))
		finally:
			os.remove(path)
			for c in (code, ausente):
				if frappe.db.exists("Item", c):
					frappe.delete_doc("Item", c, force=True, ignore_permissions=True)
			frappe.db.commit()  # nosemgrep — limpieza de fixtures de test

	def test_print_format_seeding_e_idempotencia(self):
		"""Capacidad genérica: crea un Print Format desde html_file/css_file (assets externos),
		compone el html con <style>, es idempotente y NUNCA toca un Print Format PROTEGIDO."""
		import os
		import tempfile

		pf_name = "_DEMO Print Format PSP"
		tmpdir = tempfile.mkdtemp()
		try:
			html_body = '<div class="x">Hola {{ doc.name }}</div>'
			css = ".x { color: #111; }"
			os.makedirs(os.path.join(tmpdir, "print_formats"))
			with open(os.path.join(tmpdir, "print_formats", "demo.html"), "w", encoding="utf-8") as fh:
				fh.write(html_body)
			with open(os.path.join(tmpdir, "print_formats", "demo.css"), "w", encoding="utf-8") as fh:
				fh.write(css)
			catalog = {
				"version": "t",
				"catalog": "demo_pf",
				"sections": [],
				"versioned": [],
				"print_formats": [
					{
						"name": pf_name,
						"doc_type": "Quotation",
						"print_format_type": "Jinja",
						"standard": "No",
						"custom_format": 1,
						"html_file": "print_formats/demo.html",
						"css_file": "print_formats/demo.css",
					}
				],
			}
			path = os.path.join(tmpdir, "catalog.json")
			with open(path, "w", encoding="utf-8") as fh:
				json.dump(catalog, fh)

			catalog_loader.run(catalog_path=path, dry_run=False)
			self.assertTrue(frappe.db.exists("Print Format", pf_name))
			stored = frappe.db.get_value("Print Format", pf_name, ["html", "css", "standard"], as_dict=True)
			self.assertIn(css, stored.html)  # el <style> autocontiene el css
			self.assertIn(html_body, stored.html)
			self.assertEqual(stored.css, css)
			self.assertEqual(stored.standard, "No")

			rep2 = catalog_loader.run(catalog_path=path, dry_run=False)  # idempotencia
			self.assertEqual(len(rep2["created"]), 0)
			self.assertEqual(len(rep2["updated"]), 0)
			self.assertEqual(len(rep2["conflicts"]), 0)
		finally:
			if frappe.db.exists("Print Format", pf_name):
				frappe.delete_doc("Print Format", pf_name, force=True, ignore_permissions=True)
			for f in ("print_formats/demo.html", "print_formats/demo.css", "catalog.json"):
				fp = os.path.join(tmpdir, f)
				if os.path.exists(fp):
					os.remove(fp)
			os.rmdir(os.path.join(tmpdir, "print_formats"))
			os.rmdir(tmpdir)
			frappe.db.commit()  # nosemgrep — limpieza de fixtures de test

	def test_print_format_renderer_profile_seeded(self):
		"""v10 (ADR-0015): el catálogo puede declarar `proposal_renderer_profile` y el seeder lo
		administra como campo del Print Format (igual que html/css), habilitando la adopción de Gotenberg."""
		import os
		import tempfile

		pf_name = "_DEMO PF Gotenberg"
		tmpdir = tempfile.mkdtemp()
		try:
			catalog = {
				"version": "t",
				"catalog": "demo_pf_rp",
				"sections": [],
				"versioned": [],
				"print_formats": [
					{
						"name": pf_name,
						"doc_type": "Quotation",
						"print_format_type": "Jinja",
						"standard": "No",
						"custom_format": 1,
						"html": "<div>x</div>",
						"proposal_renderer_profile": "gotenberg-v1",
					}
				],
			}
			path = os.path.join(tmpdir, "catalog.json")
			with open(path, "w", encoding="utf-8") as fh:
				json.dump(catalog, fh)

			catalog_loader.run(catalog_path=path, dry_run=False)
			self.assertEqual(
				frappe.db.get_value("Print Format", pf_name, "proposal_renderer_profile"),
				"gotenberg-v1",
			)
			# idempotente: re-correr no reporta cambios
			rep2 = catalog_loader.run(catalog_path=path, dry_run=False)
			self.assertEqual(len(rep2["updated"]), 0)
			self.assertEqual(len(rep2["conflicts"]), 0)
		finally:
			if frappe.db.exists("Print Format", pf_name):
				frappe.delete_doc("Print Format", pf_name, force=True, ignore_permissions=True)
			if os.path.exists(os.path.join(tmpdir, "catalog.json")):
				os.remove(os.path.join(tmpdir, "catalog.json"))
			os.rmdir(tmpdir)
			frappe.db.commit()  # nosemgrep — limpieza de fixtures de test

	def test_capabilities_contrato_v12(self):
		"""caps expone renderer_profile, caps_version>=12, la garantía no_functional_master_writes, y
		YA NO expone las capacidades retiradas (contrato para el instalador)."""
		caps = catalog_loader.capabilities()
		self.assertTrue(caps["renderer_profile"])
		self.assertGreaterEqual(caps["caps_version"], 12)
		self.assertTrue(caps["no_functional_master_writes"])
		for retirada in (
			"designations_skills",
			"phase_tags",
			"payment_terms",
			"economic_behavior_rules",
			"scope_pmo_planning",
		):
			self.assertNotIn(retirada, caps, f"la capacidad retirada '{retirada}' no debe exponerse")

	def test_print_format_protegido_nunca_se_modifica(self):
		"""Un Print Format en PROTECTED_PRINT_FORMATS se reporta como conflicto y jamás se escribe,
		aunque el catálogo intente administrarlo."""
		import os
		import tempfile

		protegido = next(iter(catalog_loader.PROTECTED_PRINT_FORMATS))
		if not frappe.db.exists("Print Format", protegido):
			self.skipTest(f"{protegido} no está instalado en este site de test")
		before = frappe.db.get_value("Print Format", protegido, "html")

		tmpdir = tempfile.mkdtemp()
		try:
			catalog = {
				"version": "t",
				"catalog": "demo_protegido",
				"sections": [],
				"versioned": [],
				"print_formats": [
					{"name": protegido, "doc_type": "Quotation", "html": "<div>HACKEADO</div>"}
				],
			}
			path = os.path.join(tmpdir, "catalog.json")
			with open(path, "w", encoding="utf-8") as fh:
				json.dump(catalog, fh)
			rep = catalog_loader.run(catalog_path=path, dry_run=False, update_content=True)
			self.assertTrue(any(protegido in c and "PROTEGIDO" in c for c in rep["conflicts"]))
			self.assertEqual(frappe.db.get_value("Print Format", protegido, "html"), before)
		finally:
			if os.path.exists(os.path.join(tmpdir, "catalog.json")):
				os.remove(os.path.join(tmpdir, "catalog.json"))
			os.rmdir(tmpdir)
			frappe.db.commit()  # nosemgrep — limpieza de fixtures de test

	def test_nunca_crea_masters_fiscales(self):
		"""El loader NO tiene capacidad de sembrar UOM ni Item Groups (masters fiscales de
		facturacion_mexico): aunque un catálogo los liste, se ignoran y NO se crea ninguno."""
		import os
		import tempfile

		grp, uom = "_DEMO-GRP-NO-CREAR", "_DEMO-UOM-NO-CREAR"
		fd, path = tempfile.mkstemp(suffix=".json")
		os.close(fd)
		catalog = {
			"version": "t",
			"catalog": "demo_fiscal",
			"sections": [],
			"versioned": [],
			"item_groups": [{"item_group_name": grp, "parent_item_group": "All Item Groups"}],
			"uoms": [{"uom_name": uom}],
		}
		try:
			with open(path, "w", encoding="utf-8") as fh:
				json.dump(catalog, fh)
			catalog_loader.run(catalog_path=path, dry_run=False)  # no debe crear nada de esas claves
			self.assertFalse(frappe.db.exists("Item Group", grp))
			self.assertFalse(frappe.db.exists("UOM", uom))
			# las funciones de seeding fiscal no existen en el loader
			self.assertFalse(hasattr(catalog_loader, "_seed_item_groups"))
			self.assertFalse(hasattr(catalog_loader, "_seed_uoms"))
		finally:
			os.remove(path)
			frappe.db.rollback()

	def test_loader_no_toca_doctypes_fuera_de_allowlist(self):
		"""Límite de la allowlist tras la depuración: el loader SOLO sabe sembrar los DocTypes
		editoriales/de presentación (Sections, contenido de Item, Letter Heads, Print Formats + versiones).
		NO expone seeders para los maestros funcionales (ahora en Desk) ni para transaccionales/fiscales;
		por construcción no puede crear/modificar/eliminar esos registros."""
		prohibidos = [
			# Maestros funcionales RETIRADOS del pack (se administran en Desk) — su ausencia queda fijada.
			"_seed_phases",
			"_seed_scope_items",
			"_seed_scope_dependencies",
			"_seed_templates",
			"_seed_payment_terms",
			"_seed_payment_terms_templates",
			"_seed_designations",
			"_seed_skills",
			"_seed_economic_behavior_rules",
			"_apply_phase_tags",
			# Transaccionales / fiscales que el loader nunca gestionó.
			"_seed_quotations",
			"_seed_sales_orders",
			"_seed_customers",
			"_seed_contacts",
			"_seed_terms",
			"_seed_terms_and_conditions",
			"_seed_accounts",
			"_seed_cost_centers",
			"_seed_taxes",
			"_seed_uoms",
			"_seed_item_groups",
		]
		for fn in prohibidos:
			self.assertFalse(hasattr(catalog_loader, fn), f"el loader NO debe poder sembrar '{fn}'")

		permitidos = [
			"_seed_sections",
			"_seed_items",
			"_seed_letter_heads",
			"_seed_print_formats",
			"_seed_print_format_versions",
			"_seed_clear_fields",
		]
		for fn in permitidos:
			self.assertTrue(hasattr(catalog_loader, fn), f"falta el seeder permitido '{fn}'")

		# el loader nunca borra: no expone ninguna capacidad de eliminación
		import inspect

		src = inspect.getsource(catalog_loader)
		self.assertNotIn("delete_doc", src, "el loader jamás debe borrar registros")
