"""Tests del loader genérico de catálogos (catalog_loader) con el catálogo de ejemplo ficticio.

Cubre: dry_run sin escrituras, carga real, idempotencia, update_content, conflictos y que las
Sections base no se creen/modifiquen. No usa datos de ningún cliente.
"""

import json
import unittest

import frappe

from erpnext_proposals.erpnext_proposals.catalog_data import catalog_loader

DEMO_PHASES = ["INICIO_DEMO", "CIERRE_DEMO"]
DEMO_SECTIONS = ["Presentación Demo", "Alcance Demo"]
DEMO_TEMPLATE = "Plantilla Demo"
DEMO_SCOPE = ["DEMO-ACT-1", "DEMO-PMO"]


def _sample() -> dict:
	with open(catalog_loader.SAMPLE_CATALOG, encoding="utf-8") as fh:
		return json.load(fh)


def _cleanup() -> None:
	for c in DEMO_SCOPE:
		if frappe.db.exists("Scope Item", c):
			frappe.delete_doc("Scope Item", c, force=True, ignore_permissions=True)
	if frappe.db.exists("Proposal Template", DEMO_TEMPLATE):
		frappe.delete_doc("Proposal Template", DEMO_TEMPLATE, force=True, ignore_permissions=True)
	for s in DEMO_SECTIONS:
		if frappe.db.exists("Proposal Section", s):
			frappe.delete_doc("Proposal Section", s, force=True, ignore_permissions=True)
	for p in DEMO_PHASES:
		if frappe.db.exists("Proposal Phase", p):
			frappe.delete_doc("Proposal Phase", p, force=True, ignore_permissions=True)
	frappe.db.commit()  # nosemgrep — limpieza de fixtures de test


class TestCatalogLoader(unittest.TestCase):
	def tearDown(self):
		_cleanup()

	def test_dry_run_no_escribe(self):
		rep = catalog_loader.run(dry_run=True)
		self.assertTrue(rep["created"], "dry-run debe reportar registros por crear")
		self.assertFalse(frappe.db.exists("Proposal Phase", "INICIO_DEMO"))
		self.assertFalse(frappe.db.exists("Scope Item", "DEMO-ACT-1"))
		self.assertFalse(frappe.db.exists("Proposal Template", DEMO_TEMPLATE))

	def test_carga_real_e_idempotencia(self):
		catalog_loader.run(dry_run=False)
		self.assertTrue(frappe.db.exists("Proposal Phase", "INICIO_DEMO"))
		self.assertTrue(frappe.db.exists("Proposal Section", "Presentación Demo"))
		self.assertTrue(frappe.db.exists("Proposal Template", DEMO_TEMPLATE))
		self.assertEqual(int(frappe.db.get_value("Scope Item", "DEMO-PMO", "is_internal_cost_task")), 1)
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

	def test_items_y_scope_erpnext_item(self):
		"""Capacidad genérica: crea ERPNext Item, liga erpnext_item en el Scope Item base y deja
		el Scope Item modular SIN erpnext_item. Idempotente. Datos ficticios (no de cliente)."""
		import os
		import tempfile

		item_code, phase = "_DEMO-SVC-ITEM", "FASE_DEMO_ITEMS"
		linked, modular = "_DEMO-SC-LINKED", "_DEMO-SC-MODULAR"
		grp = (
			"Services"
			if frappe.db.exists("Item Group", "Services")
			else frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		)
		uom = "Nos" if frappe.db.exists("UOM", "Nos") else frappe.db.get_value("UOM", {}, "name")
		catalog = {
			"version": "t",
			"catalog": "demo_items",
			"phases": [{"phase_code": phase, "phase_name": phase, "sequence": 5}],
			"sections": [],
			"versioned": [],
			"items": [
				{
					"item_code": item_code,
					"item_name": "Demo SVC",
					"item_group": grp,
					"stock_uom": uom,
					"is_stock_item": 0,
					"is_sales_item": 1,
				}
			],
			"scope_items": [
				{
					"code": linked,
					"title": "Linked",
					"sequence": 10,
					"phase": phase,
					"erpnext_item": item_code,
				},
				{"code": modular, "title": "Modular", "sequence": 20, "phase": phase},
			],
			"templates": [],
		}
		fd, path = tempfile.mkstemp(suffix=".json")
		try:
			with os.fdopen(fd, "w", encoding="utf-8") as fh:
				json.dump(catalog, fh)
			catalog_loader.run(catalog_path=path, dry_run=False)
			self.assertTrue(frappe.db.exists("Item", item_code))
			self.assertEqual(frappe.db.get_value("Scope Item", linked, "erpnext_item"), item_code)
			self.assertFalse(frappe.db.get_value("Scope Item", modular, "erpnext_item"))
			rep2 = catalog_loader.run(catalog_path=path, dry_run=False)  # idempotencia
			self.assertEqual(len(rep2["created"]), 0)
			self.assertEqual(len(rep2["updated"]), 0)
			self.assertEqual(len(rep2["conflicts"]), 0)
		finally:
			os.remove(path)
			for c in (linked, modular):
				if frappe.db.exists("Scope Item", c):
					frappe.delete_doc("Scope Item", c, force=True, ignore_permissions=True)
			if frappe.db.exists("Item", item_code):
				frappe.delete_doc("Item", item_code, force=True, ignore_permissions=True)
			if frappe.db.exists("Proposal Phase", phase):
				frappe.delete_doc("Proposal Phase", phase, force=True, ignore_permissions=True)
			frappe.db.commit()  # nosemgrep — limpieza de fixtures de test

	def test_template_section_hide_title(self):
		"""El loader genérico siembra y diffea hide_title en Proposal Template Section."""
		import os
		import tempfile

		sec, tmpl = "_DEMO-SEC-HIDE", "_DEMO-TMPL-HIDE"

		def _catalog(hide):
			row = {"proposal_section": sec, "sequence": 10, "include_by_default": 1}
			if hide is not None:
				row["hide_title"] = hide
			return {
				"version": "t",
				"catalog": "demo_hide",
				"phases": [],
				"versioned": [],
				"sections": [{"section_name": sec, "title": "Demo Sec", "content": "<p>c</p>", "enabled": 1}],
				"items": [],
				"scope_items": [],
				"templates": [{"template_name": tmpl, "sections": [row]}],
			}

		def _run(cat, **kw):
			fd, path = tempfile.mkstemp(suffix=".json")
			try:
				with os.fdopen(fd, "w", encoding="utf-8") as fh:
					json.dump(cat, fh)
				return catalog_loader.run(catalog_path=path, dry_run=False, **kw)
			finally:
				os.remove(path)

		def _hide():
			return int(frappe.get_doc("Proposal Template", tmpl).sections[0].hide_title or 0)

		try:
			# hide_title=1 se siembra
			_run(_catalog(1))
			self.assertEqual(_hide(), 1, "El loader siembra hide_title=1")
			# segundo dry-run/carga idempotente
			rep2 = _run(_catalog(1))
			self.assertEqual(len(rep2["updated"]), 0)
			self.assertEqual(len(rep2["conflicts"]), 0)
			# cambio a 0 con update_content se detecta y aplica
			rep3 = _run(_catalog(0), update_content=True)
			self.assertTrue(
				any(tmpl in u for u in rep3["updated"]), "El diff detecta el cambio de hide_title"
			)
			self.assertEqual(_hide(), 0)
			# catálogo SIN la clave se comporta como 0 (default) e idempotente
			rep4 = _run(_catalog(None))
			self.assertEqual(len(rep4["updated"]), 0, "Ausencia de hide_title == 0, sin cambios")
			self.assertEqual(_hide(), 0)
		finally:
			if frappe.db.exists("Proposal Template", tmpl):
				frappe.delete_doc("Proposal Template", tmpl, force=True, ignore_permissions=True)
			if frappe.db.exists("Proposal Section", sec):
				frappe.delete_doc("Proposal Section", sec, force=True, ignore_permissions=True)
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
				"phases": [],
				"sections": [],
				"versioned": [],
				"items": [],
				"scope_items": [],
				"templates": [],
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
				"phases": [],
				"sections": [],
				"versioned": [],
				"items": [],
				"scope_items": [],
				"templates": [],
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

	def test_scope_item_erpnext_item_null_explicito(self):
		"""El catálogo puede LIMPIAR erpnext_item con null explícito (distinto de omitir la clave).
		Un Scope Item ligado a un Item deja de estarlo (no autogenera) tras aplicar erpnext_item=null."""
		import os
		import tempfile

		item, sc = "_DEMO-ITEM-NULL", "_DEMO-SC-NULL"
		grp = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		uom = "Nos" if frappe.db.exists("UOM", "Nos") else frappe.db.get_value("UOM", {}, "name")
		fd, path = tempfile.mkstemp(suffix=".json")
		os.close(fd)

		def _cat(erpnext_item_value, present):
			sc_row = {"code": sc, "title": "SC", "sequence": 10}
			if present:
				sc_row["erpnext_item"] = erpnext_item_value
			return {
				"version": "t",
				"catalog": "demo_null",
				"phases": [],
				"sections": [],
				"versioned": [],
				"items": [
					{
						"item_code": item,
						"item_name": "N",
						"item_group": grp,
						"stock_uom": uom,
						"is_stock_item": 0,
					}
				],
				"scope_items": [sc_row],
				"templates": [],
			}

		try:
			# 1) ligado a item
			with open(path, "w", encoding="utf-8") as fh:
				json.dump(_cat(item, present=True), fh)
			catalog_loader.run(catalog_path=path, dry_run=False)
			self.assertEqual(frappe.db.get_value("Scope Item", sc, "erpnext_item"), item)

			# 2) null explícito → limpia
			with open(path, "w", encoding="utf-8") as fh:
				json.dump(_cat(None, present=True), fh)
			rep = catalog_loader.run(catalog_path=path, dry_run=False, update_content=True)
			self.assertTrue(any(sc in u and "null" in u for u in rep["updated"]))
			self.assertFalse(frappe.db.get_value("Scope Item", sc, "erpnext_item"))

			# 3) idempotente: segundo null no vuelve a actualizar
			rep2 = catalog_loader.run(catalog_path=path, dry_run=False, update_content=True)
			self.assertFalse(any(sc in u for u in rep2["updated"]))
		finally:
			os.remove(path)
			if frappe.db.exists("Scope Item", sc):
				frappe.delete_doc("Scope Item", sc, force=True, ignore_permissions=True)
			if frappe.db.exists("Item", item):
				frappe.delete_doc("Item", item, force=True, ignore_permissions=True)
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
			"phases": [],
			"sections": [],
			"versioned": [],
			"item_groups": [{"item_group_name": grp, "parent_item_group": "All Item Groups"}],
			"uoms": [{"uom_name": uom}],
			"items": [],
			"scope_items": [],
			"templates": [],
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
		"""Límite de la allowlist: el loader SOLO sabe sembrar los DocTypes autorizados (Phases,
		Sections, Items, Scope Items, Print Formats, Templates, Payment Terms). NO expone seeders
		para Quotation, Sales Order, Customer, Contact, Terms and Conditions, Account, Cost Center,
		UOM ni Item Group; por construcción no puede crear/modificar/eliminar esos registros."""
		prohibidos = [
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
			"_seed_phases",
			"_seed_sections",
			"_seed_items",
			"_seed_scope_items",
			"_seed_print_formats",
			"_seed_templates",
		]
		for fn in permitidos:
			self.assertTrue(hasattr(catalog_loader, fn), f"falta el seeder permitido '{fn}'")

		# el loader nunca borra: no expone ninguna capacidad de eliminación
		import inspect

		src = inspect.getsource(catalog_loader)
		self.assertNotIn("delete_doc", src, "el loader jamás debe borrar registros")
