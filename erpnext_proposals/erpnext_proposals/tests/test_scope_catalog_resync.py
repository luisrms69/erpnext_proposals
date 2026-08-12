"""Pruebas de resync_scope_from_catalog (Issue #27).

Sincronización explícita del alcance con el catálogo Scope Item, solo en Borrador:
- update de filas auto_generated=1 con los campos controlados por catálogo,
- remove de filas sin respaldo (Scope Item deshabilitado/borrado o Item quitado),
- add de combinaciones nuevas,
- preservación de filas auto_generated=0 y de campos ajenos al catálogo,
- idempotencia (conteos reales),
- guardas de servidor por separado y permiso de escritura.

Fuera de alcance de estas pruebas: phase→Link, manual_override.
"""

import unittest

import frappe
from frappe.exceptions import PermissionError as FrappePermissionError
from frappe.exceptions import ValidationError

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.tests.phases import (
	cleanup_test_phases,
	ensure_test_phases,
)
from erpnext_proposals.erpnext_proposals.utils.quotation import resync_scope_from_catalog

TEMPLATE = "_Test Resync Template"
ITEM_A = "_Test Resync Item A"
ITEM_B = "_Test Resync Item B"
DESIG = "_Test Resync Desig"
ACT = "_Test Resync Act"
NOPERM_USER = "_test_resync_noperm@example.com"

CONTROLLED_FIELDS = (
	"sequence",
	"code",
	"title",
	"description",
	"deliverable",
	"phase",
	"activity_type",
	"designation",
	"estimated_hours",
)


class TestScopeCatalogResync(unittest.TestCase):
	# ── Setup ──────────────────────────────────────────────────────────────────

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._quotations = []
		cls._setup_master_data()
		cls._created_phases = ensure_test_phases()
		cls._setup_catalog()
		cls._created_fy = ensure_current_fiscal_year()

	@classmethod
	def tearDownClass(cls):
		for name in cls._quotations:
			if frappe.db.exists("Quotation", name):
				try:
					doc = frappe.get_doc("Quotation", name)
					if doc.docstatus == 1:
						doc.flags.ignore_linked_doctypes = True
						doc.cancel()
					frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
				except Exception:
					pass
		# Scope Items de prueba (incluye posibles extra creados en tests: _RESYNC_A4)
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_RESYNC_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		if frappe.db.exists("User", NOPERM_USER):
			frappe.delete_doc("User", NOPERM_USER, force=True, ignore_permissions=True)
		cleanup_test_phases(getattr(cls, "_created_phases", None))
		cleanup_fiscal_year(getattr(cls, "_created_fy", None))
		super().tearDownClass()

	@classmethod
	def _setup_master_data(cls):
		from erpnext_proposals.erpnext_proposals.tests.company import (
			get_test_company,
			get_test_item_group,
		)

		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company found on test site — run bench migrate first.")

		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		if not cg:
			raise unittest.SkipTest("No Customer Group found. Run ci_pre_tests first.")
		terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or frappe.db.get_value(
			"Territory", {}, "name"
		)

		if not frappe.db.exists("Customer", "_Test Resync Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test Resync Customer",
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test Resync Customer"

		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)

		ig = get_test_item_group()
		for code in (ITEM_A, ITEM_B):
			if not frappe.db.exists("Item", code):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_name": code,
						"item_group": ig,
						"stock_uom": "Nos",
						"is_stock_item": 0,
						"is_sales_item": 1,
					}
				).insert(ignore_permissions=True)

		if not frappe.db.exists("Designation", DESIG):
			frappe.get_doc({"doctype": "Designation", "designation_name": DESIG}).insert(
				ignore_permissions=True
			)
		if not frappe.db.exists("Activity Type", ACT):
			frappe.get_doc({"doctype": "Activity Type", "activity_type": ACT}).insert(ignore_permissions=True)

		cls.cost_center = frappe.db.get_value(
			"Cost Center", {"is_group": 0, "company": cls.company}, "name"
		) or frappe.db.get_value("Cost Center", {"is_group": 0}, "name")

		# Usuario sin permiso de escritura sobre Quotation (sin roles).
		if not frappe.db.exists("User", NOPERM_USER):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": NOPERM_USER,
					"first_name": "Resync NoPerm",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
			# Quitar cualquier rol por defecto para garantizar ausencia de permisos.
			u = frappe.get_doc("User", NOPERM_USER)
			u.set("roles", [])
			u.save(ignore_permissions=True)

	@classmethod
	def _setup_catalog(cls):
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "Test"}
			).insert(ignore_permissions=True)

		specs = [
			("_RESYNC_A1", "Alcance A1", ITEM_A, "DISC", 10),
			("_RESYNC_A2", "Alcance A2", ITEM_A, "IMPL", 20),
			("_RESYNC_A3", "Alcance A3", ITEM_A, "GOLIVE", 5),
			("_RESYNC_B1", "Alcance B1", ITEM_B, "IMPL", 8),
		]
		for i, (code, title, item, phase, hrs) in enumerate(specs, start=1):
			if frappe.db.exists("Scope Item", code):
				continue
			frappe.get_doc(
				{
					"doctype": "Scope Item",
					"code": code,
					"title": title,
					"sequence": i,
					"erpnext_item": item,
					"phase": phase,
					"estimated_hours": hrs,
					"enabled": 1,
					"visible_in_proposal": 1,
				}
			).insert(ignore_permissions=True)

	# ── Helpers ────────────────────────────────────────────────────────────────

	def _make_quotation(self, item_codes):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "RESYNC-" + frappe.generate_hash(length=8),
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cost_center,
				"items": [
					{"item_code": c, "item_name": c, "qty": 1, "rate": 1000, "uom": "Nos"} for c in item_codes
				],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._quotations.append(doc.name)
		return doc

	@staticmethod
	def _rows(name):
		return frappe.get_doc("Quotation", name).quotation_scope_items

	@staticmethod
	def _row_by_scope(name, scope):
		return next(r for r in TestScopeCatalogResync._rows(name) if r.scope_item == scope)

	# ── A. Add ──────────────────────────────────────────────────────────────────

	def test_06_add_new_catalog_scope_item(self):
		q = self._make_quotation([ITEM_A])
		self.assertEqual(len(q.quotation_scope_items), 3)

		frappe.get_doc(
			{
				"doctype": "Scope Item",
				"code": "_RESYNC_A4",
				"title": "Alcance A4",
				"sequence": 4,
				"erpnext_item": ITEM_A,
				"phase": "GOLIVE",
				"estimated_hours": 4,
				"enabled": 1,
				"visible_in_proposal": 1,
			}
		).insert(ignore_permissions=True)
		try:
			res = resync_scope_from_catalog(q.name)
			rows = self._rows(q.name)
			keys = [(r.item_code, r.scope_item) for r in rows]
			self.assertEqual(res["added"], 1)
			self.assertEqual(len(rows), 4)
			self.assertIn((ITEM_A, "_RESYNC_A4"), keys)
			self.assertEqual(len(keys), len(set(keys)), "No debe haber claves duplicadas")
			new_row = self._row_by_scope(q.name, "_RESYNC_A4")
			self.assertEqual(new_row.auto_generated, 1)
		finally:
			frappe.delete_doc("Scope Item", "_RESYNC_A4", force=True, ignore_permissions=True)

	# ── B. Idempotencia ─────────────────────────────────────────────────────────

	def test_07_idempotent_zero_counts(self):
		q = self._make_quotation([ITEM_A])
		resync_scope_from_catalog(q.name)  # normaliza
		before = {r.scope_item: {f: r.get(f) for f in CONTROLLED_FIELDS} for r in self._rows(q.name)}
		res = resync_scope_from_catalog(q.name)  # segunda pasada sin cambios
		self.assertEqual(res["added"], 0)
		self.assertEqual(res["removed"], 0)
		self.assertEqual(res["updated"], 0, "updated solo debe contar cambios reales")
		after = {r.scope_item: {f: r.get(f) for f in CONTROLLED_FIELDS} for r in self._rows(q.name)}
		self.assertEqual(before, after, "Las filas no deben cambiar en una re-sync idempotente")
		keys = [(r.item_code, r.scope_item) for r in self._rows(q.name)]
		self.assertEqual(len(keys), len(set(keys)))

	# ── C. Todos los campos controlados + mapeo ─────────────────────────────────

	def test_01_update_reflects_all_controlled_fields(self):
		q = self._make_quotation([ITEM_A])
		si = frappe.get_doc("Scope Item", "_RESYNC_A1")
		orig = {
			"title": si.title,
			"description": si.description,
			"deliverable": si.deliverable,
			"phase": si.phase,
			"estimated_hours": si.estimated_hours,
			"default_designation": si.default_designation,
			"default_activity_type": si.default_activity_type,
			"sequence": si.sequence,
		}
		si.title = "A1 nuevo"
		si.description = "desc nueva"
		si.deliverable = "entregable nuevo"
		si.phase = "GOLIVE"
		si.estimated_hours = 77
		si.default_designation = DESIG
		si.default_activity_type = ACT
		si.sequence = 42
		si.save(ignore_permissions=True)
		try:
			resync_scope_from_catalog(q.name)
			row = self._row_by_scope(q.name, "_RESYNC_A1")
			checks = {
				"title": "A1 nuevo",
				"description": "desc nueva",
				"deliverable": "entregable nuevo",
				"phase": "GOLIVE",
				"estimated_hours": 77,
				"sequence": 42,
				"designation": DESIG,  # mapeo default_designation → designation
				"activity_type": ACT,  # mapeo default_activity_type → activity_type
				"code": "_RESYNC_A1",  # code == name del Scope Item
			}
			for field, expected in checks.items():
				with self.subTest(field=field):
					self.assertEqual(row.get(field), expected)
		finally:
			for k, v in orig.items():
				si.set(k, v)
			si.save(ignore_permissions=True)

	# ── D. Preservar campos ajenos al catálogo ──────────────────────────────────

	def test_08_preserves_non_catalog_fields(self):
		q = self._make_quotation([ITEM_A])
		row = next(r for r in q.quotation_scope_items if r.scope_item == "_RESYNC_A1")
		row.include_in_proposal = 0
		row.costing_rate = 123.45
		row.rate_source = "matrix_general"
		row.rate_locked = 1
		row.rate_locked_on = frappe.utils.now_datetime()
		q.save(ignore_permissions=True)

		si = frappe.get_doc("Scope Item", "_RESYNC_A1")
		orig_title = si.title
		si.title = "A1 v2"
		si.save(ignore_permissions=True)
		try:
			resync_scope_from_catalog(q.name)
			row = self._row_by_scope(q.name, "_RESYNC_A1")
			self.assertEqual(row.title, "A1 v2", "Campo de catálogo sí se refresca")
			self.assertEqual(row.include_in_proposal, 0)
			self.assertEqual(row.auto_generated, 1)
			self.assertEqual(float(row.costing_rate), 123.45)
			self.assertEqual(row.rate_source, "matrix_general")
			self.assertEqual(row.rate_locked, 1)
			self.assertIsNotNone(row.rate_locked_on)
		finally:
			si.title = orig_title
			si.save(ignore_permissions=True)

	# ── D3. Contenido general del Item → línea nativa Quotation Item ─────────────

	def test_item_proposal_fields_copy_and_resync(self):
		"""Congela description + proposal_* del Item en la línea nativa Quotation Item: la generación
		copia los cuatro; un guardado normal NO relee el Item; cambiar el Item no altera la línea sin
		resync; el resync explícito refresca los cuatro. Nunca vive en Quotation Scope Item."""
		if not frappe.get_meta("Quotation Item").get_field("proposal_methodology"):
			self.skipTest("requiere Quotation Item.proposal_* (bench migrate)")
		flds = ("description", "proposal_methodology", "proposal_expected_result", "proposal_scope_limit")
		item = frappe.get_doc("Item", ITEM_A)
		orig = {f: item.get(f) for f in flds}
		for f in flds:
			item.set(f, f"<p>{f} A</p>")
		item.save(ignore_permissions=True)
		try:
			# 1) generación inicial copia los 4 valores desde el Item
			q = self._make_quotation([ITEM_A])
			row = next(r for r in q.items if r.item_code == ITEM_A)
			for f in flds:
				self.assertEqual(row.get(f), f"<p>{f} A</p>", f"{f} debe congelarse en Quotation Item")
			# 7) el contenido NO vive en Quotation Scope Item
			for sr in q.quotation_scope_items:
				for f in ("proposal_methodology", "proposal_expected_result", "proposal_scope_limit"):
					self.assertIsNone(sr.get(f), f"{f} NO debe vivir en Quotation Scope Item")

			# 2/3) cambiar el Item + guardado NORMAL no relee ni altera la línea congelada
			for f in flds:
				item.set(f, f"<p>{f} B</p>")
			item.save(ignore_permissions=True)
			frappe.get_doc("Quotation", q.name).save(ignore_permissions=True)  # guardado normal
			row = next(r for r in frappe.get_doc("Quotation", q.name).items if r.item_code == ITEM_A)
			for f in flds:
				self.assertEqual(
					row.get(f), f"<p>{f} A</p>", f"{f}: un guardado normal no debe releer el Item"
				)

			# 4) resync explícito refresca los cuatro valores
			resync_scope_from_catalog(q.name)
			row = next(r for r in frappe.get_doc("Quotation", q.name).items if r.item_code == ITEM_A)
			for f in flds:
				self.assertEqual(row.get(f), f"<p>{f} B</p>", f"{f} debe refrescarse en resync (Borrador)")
		finally:
			for f, v in orig.items():
				item.set(f, v)
			item.save(ignore_permissions=True)

	# ── E. Fila manual bajo condición destructiva ───────────────────────────────

	def test_04_manual_row_survives_destructive_resync(self):
		q = self._make_quotation([ITEM_A, ITEM_B])
		q.append(
			"quotation_scope_items",
			{
				"item_code": ITEM_B,  # ligada a un Item que se va a quitar
				"title": "FILA MANUAL",
				"estimated_hours": 3,
				"include_in_proposal": 1,
				"auto_generated": 0,
			},
		)
		q.save(ignore_permissions=True)
		# Quitar Item B (destructivo para el alcance auto de B) + deshabilitar un scope de A
		q.items = [it for it in q.items if it.item_code != ITEM_B]
		q.save(ignore_permissions=True)
		si = frappe.get_doc("Scope Item", "_RESYNC_A3")
		si.enabled = 0
		si.save(ignore_permissions=True)
		try:
			resync_scope_from_catalog(q.name)
			rows = self._rows(q.name)
			manuals = [r for r in rows if not r.auto_generated]
			self.assertEqual(len(manuals), 1, "La fila manual debe sobrevivir")
			self.assertEqual(manuals[0].title, "FILA MANUAL")
			self.assertEqual(manuals[0].estimated_hours, 3)
			# El alcance auto de B fue removido; A3 deshabilitado también.
			auto_codes = {r.scope_item for r in rows if r.auto_generated}
			self.assertNotIn("_RESYNC_B1", auto_codes)
			self.assertNotIn("_RESYNC_A3", auto_codes)
		finally:
			si.enabled = 1
			si.save(ignore_permissions=True)

	# ── include_in_proposal (foco específico) ───────────────────────────────────

	def test_05_include_in_proposal_preserved(self):
		q = self._make_quotation([ITEM_A])
		row = next(r for r in q.quotation_scope_items if r.scope_item == "_RESYNC_A1")
		row.include_in_proposal = 0
		q.save(ignore_permissions=True)
		si = frappe.get_doc("Scope Item", "_RESYNC_A1")
		orig_title = si.title
		si.title = "A1 v3"
		si.save(ignore_permissions=True)
		try:
			resync_scope_from_catalog(q.name)
			row = self._row_by_scope(q.name, "_RESYNC_A1")
			self.assertEqual(row.title, "A1 v3")
			self.assertEqual(row.include_in_proposal, 0)
		finally:
			si.title = orig_title
			si.save(ignore_permissions=True)

	# ── Remove ──────────────────────────────────────────────────────────────────

	def test_02_remove_disabled_scope_item(self):
		q = self._make_quotation([ITEM_A])
		si = frappe.get_doc("Scope Item", "_RESYNC_A3")
		si.enabled = 0
		si.save(ignore_permissions=True)
		try:
			res = resync_scope_from_catalog(q.name)
			codes = {r.scope_item for r in self._rows(q.name)}
			self.assertNotIn("_RESYNC_A3", codes)
			self.assertEqual(len(codes), 2)
			self.assertEqual(res["removed"], 1)
		finally:
			si.enabled = 1
			si.save(ignore_permissions=True)

	def test_03_remove_when_item_removed(self):
		q = self._make_quotation([ITEM_A, ITEM_B])
		self.assertEqual(len(q.quotation_scope_items), 4)
		q.items = [it for it in q.items if it.item_code != ITEM_B]
		q.save(ignore_permissions=True)
		res = resync_scope_from_catalog(q.name)
		codes = {r.scope_item for r in self._rows(q.name)}
		self.assertNotIn("_RESYNC_B1", codes)
		self.assertEqual(len(codes), 3)
		self.assertEqual(res["removed"], 1)

	# ── H. Unicidad de claves / items duplicados ────────────────────────────────

	def test_09_resync_keeps_keys_unique(self):
		# La clave (item_code, scope_item) es única por construcción (un Scope Item
		# apunta a un solo Item). Se verifica que resync nunca produce filas con clave
		# duplicada, ni en la primera pasada ni en una segunda.
		q = self._make_quotation([ITEM_A, ITEM_B])
		res = resync_scope_from_catalog(q.name)
		keys = [(r.item_code, r.scope_item) for r in self._rows(q.name)]
		self.assertEqual(len(keys), len(set(keys)), "resync no debe duplicar claves")
		self.assertEqual(res["added"], 0)
		resync_scope_from_catalog(q.name)
		keys2 = [(r.item_code, r.scope_item) for r in self._rows(q.name)]
		self.assertEqual(len(keys2), len(set(keys2)))
		self.assertEqual(len(keys2), len(keys))

	def test_09b_duplicate_item_line_rejected_by_erpnext(self):
		# ERPNext bloquea líneas de Item literalmente duplicadas
		# (SellingController.validate_for_duplicate_items); por eso la clave
		# (item_code, scope_item) no puede colisionar por líneas de Item repetidas.
		with self.assertRaises(ValidationError):
			self._make_quotation([ITEM_A, ITEM_A])

	# ── F. Guardas de servidor por separado ─────────────────────────────────────

	def test_10_guard_submitted(self):
		q = self._make_quotation([ITEM_A])
		q.reload()
		q.flags.ignore_mandatory = True
		q.flags.ignore_links = True
		q.submit()
		before = len(self._rows(q.name))
		with self.assertRaises(ValidationError):
			resync_scope_from_catalog(q.name)
		self.assertEqual(len(self._rows(q.name)), before, "No debe persistir cambios")

	def test_11_guard_workflow_state_not_borrador(self):
		q = self._make_quotation([ITEM_A])
		frappe.db.set_value("Quotation", q.name, "workflow_state", "En Revision")
		before = len(self._rows(q.name))
		try:
			with self.assertRaises(ValidationError):
				resync_scope_from_catalog(q.name)
			self.assertEqual(len(self._rows(q.name)), before)
		finally:
			frappe.db.set_value("Quotation", q.name, "workflow_state", "Borrador")

	def test_12_guard_missing_template(self):
		q = self._make_quotation([ITEM_A])
		frappe.db.set_value("Quotation", q.name, "proposal_template", None)
		before = len(self._rows(q.name))
		with self.assertRaises(ValidationError):
			resync_scope_from_catalog(q.name)
		self.assertEqual(len(self._rows(q.name)), before)

	# ── G. Permiso de escritura ─────────────────────────────────────────────────

	def test_13_requires_write_permission(self):
		q = self._make_quotation([ITEM_A])
		original_user = frappe.session.user
		frappe.set_user(NOPERM_USER)
		try:
			with self.assertRaises(FrappePermissionError):
				resync_scope_from_catalog(q.name)
		finally:
			frappe.set_user(original_user)

	# ── E2E combinado (espejo del flujo de UI) ──────────────────────────────────

	def test_14_end_to_end_combined(self):
		q = self._make_quotation([ITEM_A, ITEM_B])
		# 1) editar fila manual + apagar include_in_proposal en una auto
		q.append(
			"quotation_scope_items",
			{
				"item_code": ITEM_A,
				"title": "MANUAL E2E",
				"estimated_hours": 2,
				"include_in_proposal": 1,
				"auto_generated": 0,
			},
		)
		a1 = next(r for r in q.quotation_scope_items if r.scope_item == "_RESYNC_A1")
		a1.include_in_proposal = 0
		q.save(ignore_permissions=True)
		# 2) cambiar catálogo (A2) + agregar A5
		si2 = frappe.get_doc("Scope Item", "_RESYNC_A2")
		orig2 = si2.title
		si2.title = "A2 E2E"
		si2.save(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Scope Item",
				"code": "_RESYNC_A5",
				"title": "Alcance A5",
				"sequence": 5,
				"erpnext_item": ITEM_A,
				"phase": "IMPL",
				"estimated_hours": 6,
				"enabled": 1,
				"visible_in_proposal": 1,
			}
		).insert(ignore_permissions=True)
		# 3) quitar Item B
		q.items = [it for it in q.items if it.item_code != ITEM_B]
		q.save(ignore_permissions=True)
		try:
			res = resync_scope_from_catalog(q.name)
			rows = self._rows(q.name)
			codes = {r.scope_item for r in rows}
			# A2 refrescado
			self.assertEqual(self._row_by_scope(q.name, "_RESYNC_A2").title, "A2 E2E")
			# include_in_proposal conservado
			self.assertEqual(self._row_by_scope(q.name, "_RESYNC_A1").include_in_proposal, 0)
			# A5 presente (lo agregó el autosave append-only al guardar el paso 3),
			# B1 removido por resync, fila manual intacta.
			self.assertIn("_RESYNC_A5", codes)
			self.assertNotIn("_RESYNC_B1", codes)
			manuals = [r for r in rows if not r.auto_generated]
			self.assertEqual(len(manuals), 1)
			self.assertEqual(manuals[0].title, "MANUAL E2E")
			# En el flujo real del botón el guardado (append-only) ya agregó A5, por eso
			# resync reporta added=0; su aporte neto es update (A2) + remove (B1).
			self.assertEqual(res["added"], 0)
			self.assertGreaterEqual(res["removed"], 1)
			self.assertGreaterEqual(res["updated"], 1)
			# idempotencia: segunda pasada en cero
			res2 = resync_scope_from_catalog(q.name)
			self.assertEqual((res2["added"], res2["removed"], res2["updated"]), (0, 0, 0))
		finally:
			si2.title = orig2
			si2.save(ignore_permissions=True)
			if frappe.db.exists("Scope Item", "_RESYNC_A5"):
				frappe.delete_doc("Scope Item", "_RESYNC_A5", force=True, ignore_permissions=True)

	# ── H. Freeze NUNCA resincroniza (regla absoluta) ───────────────────────────

	def test_15_freeze_does_not_resync(self):
		"""El freeze (Borrador → En Revisión, vía submit → freeze_proposal) NUNCA resincroniza contra
		catálogo. Cambiar los maestros DESPUÉS de crear el Borrador y luego congelar NO debe alterar el
		contenido ya materializado (campos de scope controlados por catálogo ni editorial del Item). El
		freeze congela lo que el usuario ya revisó; no vuelve a materializar el catálogo vigente.

		(La transición real Borrador → En Revisión usa el MISMO `freeze_proposal` + `attach_proposal_pdfs`;
		ninguno resincroniza. `attach_proposal_pdfs` solo renderiza el contenido congelado con get_print.)
		"""
		# Editorial del Item congelable en la línea Quotation Item.
		frappe.db.set_value("Item", ITEM_A, "proposal_methodology", "METODO ORIGINAL", update_modified=False)
		frappe.clear_document_cache("Item", ITEM_A)
		q = self._make_quotation([ITEM_A])
		row = self._row_by_scope(q.name, "_RESYNC_A1")
		orig_title, orig_hours = row.title, row.estimated_hours
		item_line = next(i for i in frappe.get_doc("Quotation", q.name).items if i.item_code == ITEM_A)
		self.assertEqual(item_line.proposal_methodology, "METODO ORIGINAL")

		# Cambiar los MAESTROS del catálogo DESPUÉS de crear el Borrador.
		frappe.db.set_value(
			"Scope Item",
			"_RESYNC_A1",
			{"title": "CAMBIADO FREEZE", "estimated_hours": 99},
			update_modified=False,
		)
		frappe.clear_document_cache("Scope Item", "_RESYNC_A1")
		frappe.db.set_value("Item", ITEM_A, "proposal_methodology", "METODO CAMBIADO", update_modified=False)
		frappe.clear_document_cache("Item", ITEM_A)
		try:
			# FREEZE (submit dispara freeze_proposal en before_submit).
			doc = frappe.get_doc("Quotation", q.name)
			doc.flags.ignore_mandatory = True
			doc.flags.ignore_links = True
			doc.submit()

			# El contenido congelado NO cambió: el freeze no refrescó nada desde el catálogo.
			row2 = self._row_by_scope(q.name, "_RESYNC_A1")
			self.assertEqual(row2.title, orig_title, "freeze NO debe refrescar el título del scope")
			self.assertEqual(row2.estimated_hours, orig_hours, "freeze NO debe refrescar las horas del scope")
			item2 = next(i for i in frappe.get_doc("Quotation", q.name).items if i.item_code == ITEM_A)
			self.assertEqual(
				item2.proposal_methodology,
				"METODO ORIGINAL",
				"freeze NO debe recopiar el editorial del Item desde el maestro",
			)
		finally:
			frappe.db.set_value(
				"Scope Item",
				"_RESYNC_A1",
				{"title": orig_title, "estimated_hours": orig_hours},
				update_modified=False,
			)
			frappe.db.set_value("Item", ITEM_A, "proposal_methodology", None, update_modified=False)
			frappe.clear_document_cache("Scope Item", "_RESYNC_A1")
			frappe.clear_document_cache("Item", ITEM_A)
