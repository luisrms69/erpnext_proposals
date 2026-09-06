# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Issue #55 — Paquetes de alcance sobre Required Items. Datos 100% genéricos (sin cliente/PMO).

Un "paquete de alcance" es un Item organizativo —no vendible, no comprable— que agrupa Scope Items por la
relación N:M (ADR-0016) y se incorpora a la propuesta como Required Item (ADR-0017), materializando sus
Scope Items en `quotation_scope_items` con `source_type="required"` por el flujo normal. Este módulo cubre el
núcleo (commit 1): materialización, ausencia de línea comercial, picker (`scope_package_query`), preview
(`get_scope_package_scope_items`), ocurrencias por `(source_row, scope_item)` entre paquetes solapados, y
que la relación N:M no sufre regresión."""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.company import get_test_company, get_test_item_group
from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils.project import _resolve_project_type
from erpnext_proposals.erpnext_proposals.utils.scope_item_links import (
	get_scope_package_scope_items,
	resolve_scope_items_for_item,
	scope_package_query,
)

TEMPLATE = "_Test SP Template"
ACT = "_Test SP Activity"
PHASE = "_SP_PHASE"

PKG_A = "_Test SP PkgA"  # paquete (no vendible, no comprable) → SC_A1 + SC_SHARED
PKG_B = "_Test SP PkgB"  # paquete → SC_B1 + SC_SHARED
PKG_EMPTY = "_Test SP PkgEmpty"  # no vendible/no comprable pero SIN Scope Items → NO es paquete válido
IT_SOLD = "_Test SP Sold"  # vendible con scope → NO debe aparecer como paquete
IT_BUY = "_Test SP Buy"  # comprable con scope → NO debe aparecer como paquete

# Commit 2 — Project Type: paquetes con metadata `proposal_project_type`.
TYPE_A = "_Test SP Agile"
TYPE_B = "_Test SP Cascada"
PKG_PT_A = "_Test SP PkgTypeA"  # proposal_project_type = TYPE_A
PKG_PT_A2 = "_Test SP PkgTypeA2"  # proposal_project_type = TYPE_A (mismo tipo)
PKG_PT_B = "_Test SP PkgTypeB"  # proposal_project_type = TYPE_B (distinto)


class TestScopePackages(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._quotations = []
		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company on test site — run bench migrate first.")
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
		if not frappe.db.exists("Customer", "_Test SP Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test SP Customer",
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test SP Customer"
		cls.cost_center = frappe.db.get_value(
			"Cost Center", {"is_group": 0, "company": cls.company}, "name"
		) or frappe.db.get_value("Cost Center", {"is_group": 0}, "name")

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

		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "Test"}
			).insert(ignore_permissions=True)

		def _item(code, sales, purchase):
			if not frappe.db.exists("Item", code):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_name": code,
						"item_group": ig,
						"stock_uom": "Nos",
						"is_stock_item": 0,
						"is_sales_item": sales,
						"is_purchase_item": purchase,
					}
				).insert(ignore_permissions=True)

		_item(PKG_A, 0, 0)
		_item(PKG_B, 0, 0)
		_item(PKG_EMPTY, 0, 0)
		_item(IT_SOLD, 1, 0)
		_item(IT_BUY, 0, 1)

		# Commit 2 — Project Types + paquetes con proposal_project_type (si el custom field ya está aplicado).
		for pt in (TYPE_A, TYPE_B):
			if not frappe.db.exists("Project Type", pt):
				frappe.get_doc({"doctype": "Project Type", "project_type": pt}).insert(
					ignore_permissions=True
				)
		_item(PKG_PT_A, 0, 0)
		_item(PKG_PT_A2, 0, 0)
		_item(PKG_PT_B, 0, 0)
		cls._has_pt = frappe.get_meta("Item").has_field("proposal_project_type")
		if cls._has_pt:
			frappe.db.set_value("Item", PKG_PT_A, "proposal_project_type", TYPE_A)
			frappe.db.set_value("Item", PKG_PT_A2, "proposal_project_type", TYPE_A)
			frappe.db.set_value("Item", PKG_PT_B, "proposal_project_type", TYPE_B)

		# Scope Items + N:M (child erpnext_items). SC_SHARED pertenece a PKG_A y PKG_B.
		cls._make_scope("_SP_A1", PKG_A, hours=2)
		cls._make_scope("_SP_B1", PKG_B, hours=2)
		cls._make_scope("_SP_SHARED", PKG_A, hours=1, also=PKG_B)
		cls._make_scope("_SP_SOLD", IT_SOLD, hours=1)
		cls._make_scope("_SP_BUY", IT_BUY, hours=1)
		frappe.db.commit()  # nosemgrep — fixtures de test

	@classmethod
	def tearDownClass(cls):
		for name in cls._quotations:
			if frappe.db.exists("Quotation", name):
				frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_SP_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		frappe.db.commit()  # nosemgrep — limpieza de fixtures de test
		super().tearDownClass()

	@classmethod
	def _make_scope(cls, code, item, hours, also=None):
		if frappe.db.exists("Scope Item", code):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		doc = frappe.get_doc(
			{
				"doctype": "Scope Item",
				"code": code,
				"title": code,
				"sequence": 10,
				"enabled": 1,
				"visible_in_proposal": 1,
				"estimated_hours": hours,
				"default_activity_type": ACT,
				"phase": PHASE,
				"erpnext_item": item,
			}
		)
		if also:
			doc.append("erpnext_items", {"item": also})
		doc.insert(ignore_permissions=True)

	def _make_quotation(self, sold=None, required=None):
		sold_lines = [
			{"item_code": c, "item_name": c, "qty": 1, "rate": 1000, "uom": "Nos"} for c in (sold or [])
		]
		if not sold_lines:
			# Ancla vendida rate 0 (no comprable) para que ERPNext calcule totales en propuesta solo-requeridos.
			sold_lines = [{"item_code": IT_SOLD, "item_name": IT_SOLD, "qty": 1, "rate": 0, "uom": "Nos"}]
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "SP-" + frappe.generate_hash(length=8),
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"workflow_state": "Borrador",
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cost_center,
				"items": sold_lines,
				"required_items": [{"item": c, "qty": 1, "uom": "Nos"} for c in (required or [])],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._quotations.append(doc.name)
		return doc

	def _rows(self, name):
		return frappe.get_doc("Quotation", name).quotation_scope_items

	# ─────────────────────────── Materialización ───────────────────────────

	def test_01_package_materializes_scope_as_required(self):
		q = self._make_quotation(required=[PKG_A])
		rows = [r for r in self._rows(q.name) if r.item_code == PKG_A]
		scopes = {r.scope_item for r in rows}
		self.assertEqual(scopes, {"_SP_A1", "_SP_SHARED"})
		self.assertTrue(all(r.source_type == "required" for r in rows))

	def test_02_package_not_in_quotation_items(self):
		q = self._make_quotation(sold=[IT_SOLD], required=[PKG_A])
		codes = {i.item_code for i in frappe.get_doc("Quotation", q.name).items}
		self.assertNotIn(PKG_A, codes)

	def test_03_two_packages_overlap_two_occurrences(self):
		# PKG_A y PKG_B comparten _SP_SHARED → dos ocurrencias (identidad por (source_row, scope_item)).
		q = self._make_quotation(required=[PKG_A, PKG_B])
		shared = [r for r in self._rows(q.name) if r.scope_item == "_SP_SHARED"]
		self.assertEqual(len(shared), 2)
		self.assertEqual(len({r.source_row for r in shared}), 2)  # source_row distinto por paquete

	def test_04_delete_scope_row_not_reponed_on_save(self):
		q = self._make_quotation(required=[PKG_A])
		doc = frappe.get_doc("Quotation", q.name)
		doc.quotation_scope_items = [r for r in doc.quotation_scope_items if r.scope_item != "_SP_A1"]
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertNotIn("_SP_A1", {r.scope_item for r in doc.quotation_scope_items})

	# ─────────────────────────── Picker (scope_package_query) ───────────────────────────

	def _query_names(self, txt=""):
		return {row[0] for row in scope_package_query("Item", txt, "name", 0, 50, None)}

	def test_10_query_includes_packages_with_scope(self):
		names = self._query_names()
		self.assertIn(PKG_A, names)
		self.assertIn(PKG_B, names)

	def test_11_query_excludes_sold_purchasable_and_empty(self):
		names = self._query_names()
		self.assertNotIn(IT_SOLD, names)  # vendible
		self.assertNotIn(IT_BUY, names)  # comprable
		self.assertNotIn(PKG_EMPTY, names)  # sin Scope Items

	def test_12_query_txt_filter(self):
		self.assertIn(PKG_A, self._query_names(txt="PkgA"))
		self.assertNotIn(PKG_B, self._query_names(txt="PkgA"))

	# ─────────────────────────── Preview + N:M sin regresión ───────────────────────────

	def test_20_preview_returns_scope_items(self):
		codes = {s["code"] for s in get_scope_package_scope_items(PKG_A)}
		self.assertEqual(codes, {"_SP_A1", "_SP_SHARED"})

	def test_21_nm_resolver_no_regression(self):
		self.assertEqual(
			set(resolve_scope_items_for_item(PKG_B, enabled_only=True)), {"_SP_B1", "_SP_SHARED"}
		)

	# ─────────────────────────── Project Type (commit 2) ───────────────────────────

	def _require_pt(self):
		if not self.__class__._has_pt:
			self.skipTest("custom field Item.proposal_project_type no aplicado (bench migrate pendiente)")

	def test_30_project_type_single(self):
		self._require_pt()
		q = self._make_quotation(required=[PKG_PT_A])
		self.assertEqual(_resolve_project_type(frappe.get_doc("Quotation", q.name)), TYPE_A)

	def test_31_project_type_same_type_ok(self):
		self._require_pt()
		q = self._make_quotation(required=[PKG_PT_A, PKG_PT_A2])
		self.assertEqual(_resolve_project_type(frappe.get_doc("Quotation", q.name)), TYPE_A)

	def test_32_project_type_conflict_blocks(self):
		self._require_pt()
		q = self._make_quotation(required=[PKG_PT_A, PKG_PT_B])
		with self.assertRaises(frappe.ValidationError):
			_resolve_project_type(frappe.get_doc("Quotation", q.name))

	def test_33_project_type_none_when_no_package_declares(self):
		self._require_pt()
		q = self._make_quotation(required=[PKG_A])  # paquete sin proposal_project_type
		self.assertIsNone(_resolve_project_type(frappe.get_doc("Quotation", q.name)))
