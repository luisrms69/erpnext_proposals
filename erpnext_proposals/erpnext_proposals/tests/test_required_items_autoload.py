# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Fase 1 bis — Autoload de Required Items + Scope de abastecimiento, por Company (ADR-0017). Genérico.

`Proposal Settings` es un DocType **por Company** (no Single): la resolución es estricta por
`quotation.company`, sin fallback global. Cubre la PRECARGA configurada al agregar Items vendidos nuevos
(reglas por Item y por Item Group, con precedencia de Item), sin duplicar, respetando el borrado manual, y
disparando el alcance del Required Item precargado; el Scope Item de abastecimiento híbrido (default por
Company gateado por is_purchase_item, con opt-out `proposal_skip_procurement`) en Items vendidos y
requeridos comprables, su ausencia para no comprables / opt-out, la no duplicación de una reventa, la
preservación en el resync; la **separación estricta entre Companies** (settings de A no afectan a B) y la
imposibilidad de dos `Proposal Settings` para la misma Company."""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.company import (
	get_test_company,
	get_test_cost_center,
	get_test_item_group,
)
from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils.quotation import resync_scope_from_catalog

TEMPLATE = "_RIB Template"
ACT = "_RIB Activity"
PHASE = "_RIB_PHASE"
GROUP = "_RIB Group"
COMPANY_B = "_RIB Co B"
COMPANY_B_ABBR = "_RIBB"

IT_SOLD = "_RIB Sold"  # vendido no comprable (dispara reglas de autoload)
IT_GSOLD = "_RIB GSold"  # vendido no comprable, en GROUP (dispara regla por Item Group)
IT_REQ = "_RIB Req"  # requerido comprable con scope propio
IT_REQ2 = "_RIB Req2"  # segundo requerido (precedencia y reglas por Company distintas)
IT_SOLD_BUY = "_RIB SoldBuy"  # vendido comprable → dispara paquete de compras
IT_SOLD_BUY2 = "_RIB SoldBuy2"  # segundo vendido comprable (para probar "una sola vez")
IT_SOLD_NOPUR = "_RIB SoldNoPur"  # vendido no comprable → sin abastecimiento
IT_SKIP = "_RIB Skip"  # vendido comprable con opt-out de abastecimiento

REQ_SCOPE = "_RIB_REQ_SCOPE"  # scope del Required Item precargado
# Paquetes de Gestión de Compras (issue #55): Items no vendibles/no comprables con su Scope Item de compra.
PROC_PKG = "_RIB ProcPkg"  # paquete de compras (Company A)
PROC_PKG_B = "_RIB ProcPkgB"  # paquete de compras (Company B)
PROC_SCOPE = "_RIB_PROC"  # Scope Item de compras del paquete A
PROC_SCOPE_B = "_RIB_PROC_B"  # Scope Item de compras del paquete B


class TestRequiredItemsAutoload(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._quotations = []
		cls.company_a = get_test_company()
		if not cls.company_a:
			raise unittest.SkipTest("No Company on test site — run bench migrate first.")
		cls.company_b = cls._ensure_company_b()
		cls._fy = ensure_current_fiscal_year()
		ig = get_test_item_group()
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or frappe.db.get_value(
			"Territory", {}, "name"
		)
		if not cg:
			raise unittest.SkipTest("No Customer Group on test site.")
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		if not frappe.db.exists("Customer", "_RIB Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_RIB Customer",
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_RIB Customer"
		cls.cc_a = get_test_cost_center(cls.company_a)
		cls.cc_b = get_test_cost_center(cls.company_b)

		if not frappe.db.exists("Activity Type", ACT):
			frappe.get_doc({"doctype": "Activity Type", "activity_type": ACT}).insert(ignore_permissions=True)
		frappe.db.set_value("Activity Type", ACT, "costing_rate", 100)

		if not frappe.db.exists("Proposal Phase", PHASE):
			frappe.get_doc(
				{
					"doctype": "Proposal Phase",
					"phase_code": PHASE,
					"phase_name": PHASE,
					"sequence": 10,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)

		# Item Group dedicado (para la regla por Item Group, sin contaminar el grupo compartido).
		if not frappe.db.exists("Item Group", GROUP):
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": GROUP,
					"parent_item_group": "All Item Groups",
					"is_group": 0,
				}
			).insert(ignore_permissions=True)

		def _item(code, sales, purchase, group=ig, skip=0):
			if not frappe.db.exists("Item", code):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_name": code,
						"item_group": group,
						"stock_uom": "Nos",
						"is_stock_item": 0,
						"is_sales_item": sales,
						"is_purchase_item": purchase,
					}
				).insert(ignore_permissions=True)
			if skip:
				frappe.db.set_value("Item", code, "proposal_skip_procurement", 1)

		_item(IT_SOLD, 1, 0)
		_item(IT_GSOLD, 1, 0, group=GROUP)
		_item(IT_REQ, 0, 1)
		_item(IT_REQ2, 0, 1)
		_item(IT_SOLD_BUY, 1, 1)
		_item(IT_SOLD_BUY2, 1, 1)
		_item(IT_SOLD_NOPUR, 1, 0)
		_item(IT_SKIP, 1, 1, skip=1)
		_item(PROC_PKG, 0, 0)  # paquete de compras A (no vendible, no comprable)
		_item(PROC_PKG_B, 0, 0)  # paquete de compras B

		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "Test"}
			).insert(ignore_permissions=True)

		cls._make_scope(REQ_SCOPE, IT_REQ, hours=1)  # scope ligado al Required Item precargado
		cls._make_scope(PROC_SCOPE, PROC_PKG, hours=1, visible=0)  # scope del paquete de compras A
		cls._make_scope(PROC_SCOPE_B, PROC_PKG_B, hours=1, visible=0)  # scope del paquete de compras B
		cls._clear_all_settings()
		frappe.db.commit()  # nosemgrep — fixtures de test

	@classmethod
	def tearDownClass(cls):
		for name in cls._quotations:
			if frappe.db.exists("Quotation", name):
				frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_RIB_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		cls._clear_all_settings()
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		frappe.db.commit()  # nosemgrep — limpieza de fixtures de test
		super().tearDownClass()

	def tearDown(self):
		# Aislar cada test: sin Proposal Settings para ninguna Company (estado por defecto).
		self._clear_all_settings()

	# ─────────────────────────── Helpers ────────────────────────────────────

	@classmethod
	def _ensure_company_b(cls):
		if not frappe.db.exists("Company", COMPANY_B):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": COMPANY_B,
					"abbr": COMPANY_B_ABBR,
					"default_currency": "MXN",
					"country": "Mexico",
				}
			).insert(ignore_permissions=True)
		return COMPANY_B

	@classmethod
	def _clear_all_settings(cls):
		for company in (COMPANY_B, get_test_company()):
			name = frappe.db.get_value("Proposal Settings", {"company": company}, "name")
			if name:
				frappe.delete_doc("Proposal Settings", name, force=True, ignore_permissions=True)

	@classmethod
	def _make_scope(cls, code, item, hours, visible=1):
		if frappe.db.exists("Scope Item", code):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Scope Item",
				"code": code,
				"title": code,
				"sequence": 10,
				"enabled": 1,
				"visible_in_proposal": visible,
				"estimated_hours": hours,
				"default_activity_type": ACT,
				"phase": PHASE,
				"erpnext_item": item,
			}
		).insert(ignore_permissions=True)

	@staticmethod
	def _set_settings(company, rules=None, procurement=None):
		"""Crea/actualiza el Proposal Settings de una Company concreta."""
		name = frappe.db.get_value("Proposal Settings", {"company": company}, "name")
		s = frappe.get_doc("Proposal Settings", name) if name else frappe.new_doc("Proposal Settings")
		s.company = company
		s.set("required_item_rules", [])
		for source_type, source, required_item in rules or []:
			s.append(
				"required_item_rules",
				{"source_type": source_type, "source": source, "required_item": required_item},
			)
		s.default_procurement_package_item = procurement  # Item-paquete de Gestión de Compras (issue #55)
		s.flags.ignore_permissions = True
		s.save(ignore_permissions=True)

	def _make_quotation(self, company, sold):
		cc = self.cc_a if company == self.company_a else self.cc_b
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "RIB-" + frappe.generate_hash(length=8),
				"company": company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"workflow_state": "Borrador",
				"proposal_template": TEMPLATE,
				"proposal_cost_center": cc,
				"items": [
					{"item_code": c, "item_name": c, "qty": 1, "rate": 1000, "uom": "Nos"} for c in sold
				],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._quotations.append(doc.name)
		return doc

	@staticmethod
	def _required(name):
		return [(r.item, r.auto_generated) for r in frappe.get_doc("Quotation", name).get("required_items")]

	@staticmethod
	def _scope_pairs(name):
		return {(r.item_code, r.scope_item) for r in frappe.get_doc("Quotation", name).quotation_scope_items}

	# ─────────────────────────── Autoload de Required Items ──────────────────

	def test_01_item_rule_autoloads_required(self):
		self._set_settings(self.company_a, rules=[("Item", IT_SOLD, IT_REQ)])
		q = self._make_quotation(self.company_a, sold=[IT_SOLD])
		self.assertIn((IT_REQ, 1), self._required(q.name))  # precargado y marcado auto_generated

	def test_02_item_group_rule_autoloads_required(self):
		self._set_settings(self.company_a, rules=[("Item Group", GROUP, IT_REQ)])
		q = self._make_quotation(self.company_a, sold=[IT_GSOLD])
		self.assertIn(IT_REQ, [r[0] for r in self._required(q.name)])

	def test_03_item_rule_takes_precedence_over_group(self):
		# El mismo Item vendido tiene regla específica (→ IT_REQ) y su grupo tiene regla (→ IT_REQ2).
		self._set_settings(self.company_a, rules=[("Item", IT_GSOLD, IT_REQ), ("Item Group", GROUP, IT_REQ2)])
		q = self._make_quotation(self.company_a, sold=[IT_GSOLD])
		codes = [r[0] for r in self._required(q.name)]
		self.assertIn(IT_REQ, codes)  # gana la regla específica de Item
		self.assertNotIn(IT_REQ2, codes)  # la regla de grupo no se mezcla

	def test_04_no_duplicate_when_present(self):
		self._set_settings(self.company_a, rules=[("Item", IT_SOLD, IT_REQ)])
		q = self._make_quotation(self.company_a, sold=[IT_SOLD])
		frappe.get_doc("Quotation", q.name).save(ignore_permissions=True)  # sin Items nuevos
		codes = [r[0] for r in self._required(q.name)]
		self.assertEqual(codes.count(IT_REQ), 1)

	def test_05_deleted_does_not_reappear(self):
		self._set_settings(self.company_a, rules=[("Item", IT_SOLD, IT_REQ)])
		q = self._make_quotation(self.company_a, sold=[IT_SOLD])  # precarga IT_REQ
		doc = frappe.get_doc("Quotation", q.name)
		doc.set("required_items", [r for r in doc.get("required_items") if r.item != IT_REQ])
		doc.save(ignore_permissions=True)
		frappe.get_doc("Quotation", q.name).save(ignore_permissions=True)  # sin Items nuevos
		self.assertNotIn(IT_REQ, [r[0] for r in self._required(q.name)])

	def test_06_autoloaded_required_loads_its_scope(self):
		self._set_settings(self.company_a, rules=[("Item", IT_SOLD, IT_REQ)])
		q = self._make_quotation(self.company_a, sold=[IT_SOLD])
		self.assertIn((IT_REQ, REQ_SCOPE), self._scope_pairs(q.name))

	def test_07_sold_item_not_duplicated_into_required(self):
		# Regla: IT_SOLD → requerido IT_SOLD_BUY, pero IT_SOLD_BUY ya es línea vendida → no se duplica.
		self._set_settings(self.company_a, rules=[("Item", IT_SOLD, IT_SOLD_BUY)])
		q = self._make_quotation(self.company_a, sold=[IT_SOLD, IT_SOLD_BUY])
		self.assertNotIn(IT_SOLD_BUY, [r[0] for r in self._required(q.name)])

	# ─────────────────── Paquete de Gestión de Compras (issue #55, commit 3) ───────────────────

	def test_08_sold_purchasable_adds_procurement_package(self):
		# Un vendido comprable dispara el paquete de compras UNA vez (con sus Scope Items).
		self._set_settings(self.company_a, procurement=PROC_PKG)
		q = self._make_quotation(self.company_a, sold=[IT_SOLD_BUY])
		self.assertIn(PROC_PKG, [r[0] for r in self._required(q.name)])
		self.assertIn((PROC_PKG, PROC_SCOPE), self._scope_pairs(q.name))

	def test_09_required_purchasable_adds_procurement_package(self):
		# Un requerido comprable (precargado por regla) también dispara el paquete.
		self._set_settings(self.company_a, rules=[("Item", IT_SOLD, IT_REQ)], procurement=PROC_PKG)
		q = self._make_quotation(self.company_a, sold=[IT_SOLD])  # precarga IT_REQ (comprable)
		self.assertIn(PROC_PKG, [r[0] for r in self._required(q.name)])

	def test_10_non_purchasable_no_procurement_package(self):
		self._set_settings(self.company_a, procurement=PROC_PKG)
		q = self._make_quotation(self.company_a, sold=[IT_SOLD_NOPUR])
		self.assertNotIn(PROC_PKG, [r[0] for r in self._required(q.name)])

	def test_11_skip_procurement_opt_out(self):
		self._set_settings(self.company_a, procurement=PROC_PKG)
		q = self._make_quotation(self.company_a, sold=[IT_SKIP])  # comprable pero skip=1
		self.assertNotIn(PROC_PKG, [r[0] for r in self._required(q.name)])

	def test_12_procurement_package_added_once(self):
		# DOS comprables → el paquete se agrega UNA sola vez (no por ocurrencia, a diferencia del viejo scope).
		self._set_settings(self.company_a, procurement=PROC_PKG)
		q = self._make_quotation(self.company_a, sold=[IT_SOLD_BUY, IT_SOLD_BUY2])
		self.assertEqual([r[0] for r in self._required(q.name)].count(PROC_PKG), 1)

	def test_12b_resync_preserves_procurement_scope(self):
		self._set_settings(self.company_a, procurement=PROC_PKG)
		q = self._make_quotation(self.company_a, sold=[IT_SOLD_BUY])
		resync_scope_from_catalog(q.name)  # no elimina el scope del paquete de compras
		self.assertIn((PROC_PKG, PROC_SCOPE), self._scope_pairs(q.name))

	def test_13b_procurement_no_auto_remove(self):
		# Soberanía: si el usuario borra el paquete, un re-guardado sin comprables nuevos NO lo repone.
		self._set_settings(self.company_a, procurement=PROC_PKG)
		q = self._make_quotation(self.company_a, sold=[IT_SOLD_BUY])
		self.assertIn(PROC_PKG, [r[0] for r in self._required(q.name)])
		doc = frappe.get_doc("Quotation", q.name)
		doc.required_items = [r for r in doc.required_items if r.item != PROC_PKG]
		doc.save(ignore_permissions=True)
		self.assertNotIn(PROC_PKG, [r[0] for r in self._required(q.name)])

	# ─────────────────────────── Compatibilidad Fase 1 ──────────────────────

	def test_13_no_settings_no_autoload_no_procurement(self):
		# Sin Proposal Settings para la Company: comportamiento idéntico a Fase 1.
		q = self._make_quotation(self.company_a, sold=[IT_SOLD_BUY])
		self.assertEqual(self._required(q.name), [])
		self.assertNotIn(PROC_PKG, [r[0] for r in self._required(q.name)])

	# ─────────────────────────── Separación por Company ─────────────────────

	def test_14_company_without_settings_does_not_autoload(self):
		# A tiene settings; B no. Quotation A precarga; Quotation B no precarga nada.
		self._set_settings(self.company_a, rules=[("Item", IT_SOLD, IT_REQ)])
		qa = self._make_quotation(self.company_a, sold=[IT_SOLD])
		qb = self._make_quotation(self.company_b, sold=[IT_SOLD])
		self.assertIn(IT_REQ, [r[0] for r in self._required(qa.name)])
		self.assertEqual(self._required(qb.name), [])  # sin fallback a la config de A

	def test_15_each_company_uses_only_its_own_rules(self):
		# Reglas distintas por Company; cada Quotation usa solo las suyas.
		self._set_settings(self.company_a, rules=[("Item", IT_SOLD, IT_REQ)])
		self._set_settings(self.company_b, rules=[("Item", IT_SOLD, IT_REQ2)])
		qa = self._make_quotation(self.company_a, sold=[IT_SOLD])
		qb = self._make_quotation(self.company_b, sold=[IT_SOLD])
		ra = [r[0] for r in self._required(qa.name)]
		rb = [r[0] for r in self._required(qb.name)]
		self.assertIn(IT_REQ, ra)
		self.assertNotIn(IT_REQ2, ra)
		self.assertIn(IT_REQ2, rb)
		self.assertNotIn(IT_REQ, rb)

	def test_16_procurement_package_differs_per_company(self):
		# default_procurement_package_item distinto por Company; cada Quotation usa el suyo.
		self._set_settings(self.company_a, procurement=PROC_PKG)
		self._set_settings(self.company_b, procurement=PROC_PKG_B)
		qa = self._make_quotation(self.company_a, sold=[IT_SOLD_BUY])
		qb = self._make_quotation(self.company_b, sold=[IT_SOLD_BUY])
		ra = [r[0] for r in self._required(qa.name)]
		rb = [r[0] for r in self._required(qb.name)]
		self.assertIn(PROC_PKG, ra)
		self.assertNotIn(PROC_PKG_B, ra)
		self.assertIn(PROC_PKG_B, rb)
		self.assertNotIn(PROC_PKG, rb)

	def test_17_cannot_create_two_settings_for_same_company(self):
		self._set_settings(self.company_a)  # primera config para A
		dup = frappe.new_doc("Proposal Settings")
		dup.company = self.company_a
		with self.assertRaises(frappe.exceptions.ValidationError):
			dup.insert(ignore_permissions=True)

	# ─────────── Identidad source_row de Required Items autogenerados (issue #55, fix) ───────────
	# Regresión: las filas de required_items que los autoloads agregan DENTRO del mismo validate no tenían
	# name al materializar el scope, quedando con source_row=NULL y rompiendo la identidad por ocurrencia.

	def _scope_rows(self, name, item_code):
		return [
			s for s in frappe.get_doc("Quotation", name).quotation_scope_items if s.item_code == item_code
		]

	def test_18_rule_autoloaded_required_has_real_source_row(self):
		# Required precargado por required_item_rules: su scope apunta al name REAL de la fila persistida.
		self._set_settings(self.company_a, rules=[("Item", IT_SOLD, IT_REQ)])
		q = self._make_quotation(self.company_a, sold=[IT_SOLD])
		doc = frappe.get_doc("Quotation", q.name)
		ri = next(r for r in doc.required_items if r.item == IT_REQ)
		srows = self._scope_rows(q.name, IT_REQ)
		self.assertTrue(srows, "el required autogenerado debe materializar su scope")
		for s in srows:
			self.assertTrue(s.source_row, "source_row != NULL")
			self.assertEqual(s.source_row, ri.name, "source_row == name real del Proposal Required Item")
			self.assertEqual(s.source_type, "required")

	def test_19_procurement_package_has_real_source_row(self):
		# Paquete de Gestión de Compras autoloadeado: su scope apunta al name REAL del Required Item.
		self._set_settings(self.company_a, procurement=PROC_PKG)
		q = self._make_quotation(self.company_a, sold=[IT_SOLD_BUY])
		doc = frappe.get_doc("Quotation", q.name)
		ri = next(r for r in doc.required_items if r.item == PROC_PKG)
		srows = self._scope_rows(q.name, PROC_PKG)
		self.assertTrue(srows, "el paquete de compras debe materializar su scope")
		for s in srows:
			self.assertTrue(s.source_row, "source_row != NULL")
			self.assertEqual(s.source_row, ri.name, "source_row == name real del Required Item de compras")

	def test_20_two_occurrences_differ_by_source_row(self):
		# Dos ocurrencias válidas del mismo Item-paquete se distinguen por source_row (no se colapsan).
		self._set_settings(self.company_a)  # sin reglas: control total del required_items
		q = self._make_quotation(self.company_a, sold=[IT_SOLD])
		doc = frappe.get_doc("Quotation", q.name)
		doc.append("required_items", {"item": IT_REQ, "qty": 1})
		doc.append("required_items", {"item": IT_REQ, "qty": 1})
		doc.save(ignore_permissions=True)
		doc = frappe.get_doc("Quotation", q.name)
		ri_names = {r.name for r in doc.required_items if r.item == IT_REQ}
		self.assertEqual(len(ri_names), 2, "dos filas required distintas")
		sources = {
			s.source_row
			for s in doc.quotation_scope_items
			if s.item_code == IT_REQ and s.scope_item == REQ_SCOPE
		}
		self.assertEqual(sources, ri_names, "cada ocurrencia materializa su scope con su propio source_row")

	def test_21_resync_prunes_by_source_row_membership(self):
		# La poda del resync identifica pertenencia por source_row: al quitar la ocurrencia del paquete,
		# su scope se elimina (antes, con source_row=NULL, quedaba huérfano y no se podaba).
		self._set_settings(self.company_a, procurement=PROC_PKG)
		q = self._make_quotation(self.company_a, sold=[IT_SOLD_BUY])
		self.assertIn((PROC_PKG, PROC_SCOPE), self._scope_pairs(q.name))
		doc = frappe.get_doc("Quotation", q.name)
		doc.required_items = [r for r in doc.required_items if r.item != PROC_PKG]
		doc.save(ignore_permissions=True)  # el guardado normal no repone ni poda
		self.assertIn(
			(PROC_PKG, PROC_SCOPE), self._scope_pairs(q.name), "el scope huérfano sigue hasta el resync"
		)
		resync_scope_from_catalog(q.name)
		self.assertNotIn(
			(PROC_PKG, PROC_SCOPE), self._scope_pairs(q.name), "resync poda el scope por source_row ausente"
		)


if __name__ == "__main__":
	unittest.main()
