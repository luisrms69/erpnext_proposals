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
IT_SOLD_BUY = "_RIB SoldBuy"  # vendido comprable → abastecimiento
IT_SOLD_NOPUR = "_RIB SoldNoPur"  # vendido no comprable → sin abastecimiento
IT_SKIP = "_RIB Skip"  # vendido comprable con opt-out de abastecimiento

REQ_SCOPE = "_RIB_REQ_SCOPE"  # scope del Required Item precargado
PROC_SCOPE = "_RIB_PROC"  # Scope Item de abastecimiento (Company A)
PROC_SCOPE_B = "_RIB_PROC_B"  # Scope Item de abastecimiento (Company B)


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
		_item(IT_SOLD_NOPUR, 1, 0)
		_item(IT_SKIP, 1, 1, skip=1)

		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "Test"}
			).insert(ignore_permissions=True)

		cls._make_scope(REQ_SCOPE, IT_REQ, hours=1)  # scope ligado al Required Item precargado
		cls._make_scope(PROC_SCOPE, None, hours=1, visible=0)  # abastecimiento Company A
		cls._make_scope(PROC_SCOPE_B, None, hours=1, visible=0)  # abastecimiento Company B
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
		s.default_procurement_scope_item = procurement
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

	# ─────────────────────────── Scope de abastecimiento ────────────────────

	def test_08_sold_purchasable_gets_procurement_scope(self):
		self._set_settings(self.company_a, procurement=PROC_SCOPE)
		q = self._make_quotation(self.company_a, sold=[IT_SOLD_BUY])
		self.assertIn((IT_SOLD_BUY, PROC_SCOPE), self._scope_pairs(q.name))

	def test_09_required_purchasable_gets_procurement_scope(self):
		self._set_settings(self.company_a, rules=[("Item", IT_SOLD, IT_REQ)], procurement=PROC_SCOPE)
		q = self._make_quotation(self.company_a, sold=[IT_SOLD])  # precarga IT_REQ (comprable)
		self.assertIn((IT_REQ, PROC_SCOPE), self._scope_pairs(q.name))

	def test_10_non_purchasable_no_procurement_scope(self):
		self._set_settings(self.company_a, procurement=PROC_SCOPE)
		q = self._make_quotation(self.company_a, sold=[IT_SOLD_NOPUR])
		self.assertFalse({p for p in self._scope_pairs(q.name) if p[1] == PROC_SCOPE})

	def test_11_skip_procurement_opt_out(self):
		self._set_settings(self.company_a, procurement=PROC_SCOPE)
		q = self._make_quotation(self.company_a, sold=[IT_SKIP])  # comprable pero skip=1
		self.assertFalse({p for p in self._scope_pairs(q.name) if p[1] == PROC_SCOPE})

	def test_12_resync_preserves_procurement_scope(self):
		self._set_settings(self.company_a, procurement=PROC_SCOPE)
		q = self._make_quotation(self.company_a, sold=[IT_SOLD_BUY])
		resync_scope_from_catalog(q.name)  # no debe eliminar el scope de abastecimiento
		self.assertIn((IT_SOLD_BUY, PROC_SCOPE), self._scope_pairs(q.name))

	# ─────────────────────────── Compatibilidad Fase 1 ──────────────────────

	def test_13_no_settings_no_autoload_no_procurement(self):
		# Sin Proposal Settings para la Company: comportamiento idéntico a Fase 1.
		q = self._make_quotation(self.company_a, sold=[IT_SOLD_BUY])
		self.assertEqual(self._required(q.name), [])
		self.assertFalse({p for p in self._scope_pairs(q.name) if p[1] == PROC_SCOPE})

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

	def test_16_procurement_scope_differs_per_company(self):
		# default_procurement_scope_item distinto por Company; cada Quotation usa el suyo.
		self._set_settings(self.company_a, procurement=PROC_SCOPE)
		self._set_settings(self.company_b, procurement=PROC_SCOPE_B)
		qa = self._make_quotation(self.company_a, sold=[IT_SOLD_BUY])
		qb = self._make_quotation(self.company_b, sold=[IT_SOLD_BUY])
		self.assertIn((IT_SOLD_BUY, PROC_SCOPE), self._scope_pairs(qa.name))
		self.assertNotIn((IT_SOLD_BUY, PROC_SCOPE_B), self._scope_pairs(qa.name))
		self.assertIn((IT_SOLD_BUY, PROC_SCOPE_B), self._scope_pairs(qb.name))
		self.assertNotIn((IT_SOLD_BUY, PROC_SCOPE), self._scope_pairs(qb.name))

	def test_17_cannot_create_two_settings_for_same_company(self):
		self._set_settings(self.company_a)  # primera config para A
		dup = frappe.new_doc("Proposal Settings")
		dup.company = self.company_a
		with self.assertRaises(frappe.exceptions.ValidationError):
			dup.insert(ignore_permissions=True)


if __name__ == "__main__":
	unittest.main()
