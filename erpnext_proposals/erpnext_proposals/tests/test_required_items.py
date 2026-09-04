# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Fase 1 — Required Items + modelo económico aditivo (ADR-0017). Datos 100% genéricos.

Cubre: carga de Scope Items desde Items vendidos y requeridos por el mismo resolver N:M; que un Required
Item no genera línea comercial ni ingreso; costo externo gateado por is_purchase_item y aditivo al laboral;
jerarquía de pricing nativo + fallbacks; freeze del costo externo e inmutabilidad histórica; dedup
(item_code, scope_item); Project/Tasks desde scope originado en Required Items; compatibilidad de
Quotations sin Required Items."""

import unittest

import frappe
from frappe.model.workflow import apply_workflow

from erpnext_proposals.erpnext_proposals.tests.company import get_test_company, get_test_item_group
from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils.item_cost import resolve_external_cost
from erpnext_proposals.erpnext_proposals.utils.quotation import (
	add_missing_scope_items_from_items,
	resync_scope_from_catalog,
)

TEMPLATE = "_Test RI Template"
BPL = "_Test RI Buying PL"
ACT = "_Test RI Activity"
PHASE = "_RI_PHASE"

# Items (todos genéricos).
IT_SERVICE = "_Test RI Service"  # vendido, is_purchase_item=0, con scope
IT_RESALE = "_Test RI Resale"  # vendido, is_purchase_item=1, buying price 300, con scope
IT_REQ_BUY = "_Test RI ReqBuy"  # requerido, is_purchase_item=1, buying price 300, con scope
IT_LPR = "_Test RI LPR"  # is_purchase_item=1, sin Item Price, last_purchase_rate=250
IT_VR = "_Test RI VR"  # is_purchase_item=1, sin Item Price ni LPR, valuation_rate=200
IT_NOPUR = "_Test RI NoPur"  # is_purchase_item=0


class TestRequiredItems(unittest.TestCase):
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
		if not frappe.db.exists("Customer", "_Test RI Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test RI Customer",
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test RI Customer"
		cls.cost_center = frappe.db.get_value(
			"Cost Center", {"is_group": 0, "company": cls.company}, "name"
		) or frappe.db.get_value("Cost Center", {"is_group": 0}, "name")

		# Buying Price List + Buying Settings (para get_item_price nativo).
		if not frappe.db.exists("Price List", BPL):
			frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": BPL,
					"buying": 1,
					"selling": 0,
					"currency": "MXN",
				}
			).insert(ignore_permissions=True)
		cls._prev_bpl = frappe.db.get_single_value("Buying Settings", "buying_price_list")
		frappe.db.set_single_value("Buying Settings", "buying_price_list", BPL)

		# Activity Type con costing_rate (fuente de costo laboral vía fallback de get_designation_cost).
		if not frappe.db.exists("Activity Type", ACT):
			frappe.get_doc({"doctype": "Activity Type", "activity_type": ACT}).insert(ignore_permissions=True)
		frappe.db.set_value("Activity Type", ACT, "costing_rate", 100)

		# Proposal Phase (requerida para crear Project desde el scope).
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

		_item(IT_SERVICE, 1, 0)
		_item(IT_RESALE, 1, 1)
		_item(IT_REQ_BUY, 0, 1)
		_item(IT_LPR, 0, 1)
		_item(IT_VR, 0, 1)
		_item(IT_NOPUR, 1, 0)

		# Buying Item Prices (300) para RESALE y REQ_BUY.
		for code in (IT_RESALE, IT_REQ_BUY):
			if not frappe.db.exists("Item Price", {"item_code": code, "price_list": BPL}):
				frappe.get_doc(
					{
						"doctype": "Item Price",
						"item_code": code,
						"price_list": BPL,
						"uom": "Nos",
						"price_list_rate": 300,
					}
				).insert(ignore_permissions=True)
		# Fallbacks: last_purchase_rate y valuation_rate.
		frappe.db.set_value("Item", IT_LPR, "last_purchase_rate", 250)
		frappe.db.set_value("Item", IT_VR, "valuation_rate", 200)

		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "Test"}
			).insert(ignore_permissions=True)

		# Scope Items (visibles, con horas + activity_type → costable; costo laboral = horas x 100).
		cls._make_scope("_RI_SVC", IT_SERVICE, hours=2)  # servicio propio → labor 200
		cls._make_scope("_RI_RES", IT_RESALE, hours=1)  # reventa con scope → labor 100
		cls._make_scope("_RI_REQ", IT_REQ_BUY, hours=1)  # required con scope → labor 100
		cls._make_scope("_RI_SHARED", IT_SERVICE, hours=1, also=IT_REQ_BUY)  # mismo scope, 2 Items
		frappe.db.commit()  # nosemgrep — fixtures de test

	@classmethod
	def tearDownClass(cls):
		for name in cls._quotations:
			if frappe.db.exists("Quotation", name):
				doc = frappe.get_doc("Quotation", name)
				if doc.docstatus == 1:
					for f in frappe.get_all(
						"File", {"attached_to_doctype": "Quotation", "attached_to_name": name}, pluck="name"
					):
						frappe.delete_doc("File", f, force=True, ignore_permissions=True)
					doc.flags.ignore_permissions = True
					try:
						doc.cancel()
					except Exception:
						pass
				frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_RI_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		if getattr(cls, "_prev_bpl", None) is not None:
			frappe.db.set_single_value("Buying Settings", "buying_price_list", cls._prev_bpl)
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
			# Ancla vendida rate 0 (IT_NOPUR, no comprable) para que ERPNext calcule totales cuando la
			# propuesta es solo de Required Items: net_total=0 y sin costo externo (is_purchase_item=0).
			sold_lines = [{"item_code": IT_NOPUR, "item_name": IT_NOPUR, "qty": 1, "rate": 0, "uom": "Nos"}]
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "RI-" + frappe.generate_hash(length=8),
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

	@staticmethod
	def _scope_pairs(name):
		return {(r.item_code, r.scope_item) for r in frappe.get_doc("Quotation", name).quotation_scope_items}

	def _profit(self, name):
		from erpnext_proposals.erpnext_proposals.report.profitability_estimate.profitability_estimate import (
			get_profitability_data,
		)

		return get_profitability_data(name)

	def _transition(self, doc):
		wf = frappe.db.get_value("Workflow", {"document_type": "Quotation", "is_active": 1}, "name")
		action = frappe.db.get_value(
			"Workflow Transition", {"parent": wf, "state": "Borrador", "next_state": "En Revision"}, "action"
		)
		apply_workflow(doc, action)
		doc.reload()
		return doc

	# ─────────────────────────── Scope generation ───────────────────────────

	def test_01_required_item_loads_scope(self):
		q = self._make_quotation(required=[IT_REQ_BUY])
		self.assertIn((IT_REQ_BUY, "_RI_REQ"), self._scope_pairs(q.name))

	def test_02_required_item_not_in_quotation_items(self):
		q = self._make_quotation(sold=[IT_SERVICE], required=[IT_REQ_BUY])
		codes = {i.item_code for i in frappe.get_doc("Quotation", q.name).items}
		self.assertNotIn(IT_REQ_BUY, codes)

	def test_03_required_item_no_revenue(self):
		q = self._make_quotation(required=[IT_REQ_BUY])
		self.assertEqual(self._profit(q.name)["totals"]["net_total"], 0.0)

	def test_16_dedup_item_scope_pair(self):
		q = self._make_quotation(sold=[IT_SERVICE])
		# _RI_SVC y _RI_SHARED de IT_SERVICE; guardar de nuevo no duplica.
		frappe.get_doc("Quotation", q.name).save(ignore_permissions=True)
		pairs = [
			(r.item_code, r.scope_item) for r in frappe.get_doc("Quotation", q.name).quotation_scope_items
		]
		self.assertEqual(len(pairs), len(set(pairs)))

	def test_17_same_scope_two_items_two_rows(self):
		q = self._make_quotation(sold=[IT_SERVICE], required=[IT_REQ_BUY])
		pairs = self._scope_pairs(q.name)
		self.assertIn((IT_SERVICE, "_RI_SHARED"), pairs)
		self.assertIn((IT_REQ_BUY, "_RI_SHARED"), pairs)  # dos filas, distinto item_code

	def test_18_delete_then_save_no_reappear(self):
		q = self._make_quotation(required=[IT_REQ_BUY])
		doc = frappe.get_doc("Quotation", q.name)
		doc.set("quotation_scope_items", [r for r in doc.quotation_scope_items if r.scope_item != "_RI_REQ"])
		doc.save(ignore_permissions=True)
		frappe.get_doc("Quotation", q.name).save(ignore_permissions=True)
		self.assertNotIn((IT_REQ_BUY, "_RI_REQ"), self._scope_pairs(q.name))

	def test_19_add_missing_considers_required(self):
		q = self._make_quotation(required=[IT_REQ_BUY])
		doc = frappe.get_doc("Quotation", q.name)
		doc.set("quotation_scope_items", [])
		doc.save(ignore_permissions=True)
		add_missing_scope_items_from_items(q.name)
		self.assertIn((IT_REQ_BUY, "_RI_REQ"), self._scope_pairs(q.name))

	def test_20_resync_no_readd_deleted(self):
		q = self._make_quotation(required=[IT_REQ_BUY])
		doc = frappe.get_doc("Quotation", q.name)
		doc.set("quotation_scope_items", [r for r in doc.quotation_scope_items if r.scope_item != "_RI_REQ"])
		doc.save(ignore_permissions=True)
		resync_scope_from_catalog(q.name)
		self.assertNotIn((IT_REQ_BUY, "_RI_REQ"), self._scope_pairs(q.name))

	def test_22_no_required_items_unchanged(self):
		q = self._make_quotation(sold=[IT_SERVICE])
		self.assertIn((IT_SERVICE, "_RI_SVC"), self._scope_pairs(q.name))
		self.assertEqual(frappe.get_doc("Quotation", q.name).get("required_items"), [])

	# ─────────────────────────── Costeo (resolver) ──────────────────────────

	def test_09_no_purchase_zero_external(self):
		self.assertEqual(resolve_external_cost(IT_NOPUR), (0.0, "no_purchase"))
		self.assertEqual(resolve_external_cost(IT_SERVICE), (0.0, "no_purchase"))

	def test_10_native_item_price(self):
		rate, source = resolve_external_cost(IT_RESALE, uom="Nos", transaction_date=frappe.utils.today())
		self.assertEqual((rate, source), (300.0, "buying_item_price"))

	def test_11_fallback_last_purchase(self):
		self.assertEqual(resolve_external_cost(IT_LPR), (250.0, "last_purchase_rate"))

	def test_12_fallback_valuation(self):
		self.assertEqual(resolve_external_cost(IT_VR), (200.0, "valuation_rate"))

	# ─────────────────────────── Valuación aditiva ──────────────────────────

	def test_06_service_labor_no_external(self):
		q = self._make_quotation(sold=[IT_SERVICE])
		t = self._profit(q.name)["totals"]
		self.assertEqual(t["item_cost"], 0.0)  # servicio propio → sin costo externo
		self.assertGreater(t["labor_cost"], 0.0)  # laboral desde scope

	def test_04_required_buy_external_cost(self):
		q = self._make_quotation(required=[IT_REQ_BUY])
		t = self._profit(q.name)["totals"]
		self.assertEqual(t["item_cost"], 300.0)  # externo aunque no sea línea vendida

	def test_05_required_with_scope_external_plus_labor(self):
		q = self._make_quotation(required=[IT_REQ_BUY])
		t = self._profit(q.name)["totals"]
		self.assertEqual(t["item_cost"], 300.0)
		self.assertGreater(t["labor_cost"], 0.0)  # _RI_REQ + _RI_SHARED

	def test_07_resale_revenue_plus_external(self):
		q = self._make_quotation(sold=[IT_RESALE])
		t = self._profit(q.name)["totals"]
		self.assertEqual(t["net_total"], 1000.0)
		self.assertEqual(t["item_cost"], 300.0)

	def test_08_resale_with_scope_revenue_external_labor(self):
		q = self._make_quotation(sold=[IT_RESALE])
		t = self._profit(q.name)["totals"]
		self.assertEqual(t["net_total"], 1000.0)
		self.assertEqual(t["item_cost"], 300.0)  # externo NO se anula por tener scope
		self.assertGreater(t["labor_cost"], 0.0)  # _RI_RES aporta laboral (aditivo)

	# ─────────────────────────── Freeze de costos ───────────────────────────

	def test_13_freeze_item_cost(self):
		q = self._make_quotation(sold=[IT_RESALE], required=[IT_REQ_BUY])
		doc = self._transition(frappe.get_doc("Quotation", q.name))
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(flt_first(doc.items).proposal_frozen_cost_rate, 300.0)
		self.assertEqual(flt_first(doc.items).proposal_cost_locked, 1)
		req = doc.get("required_items")[0]
		self.assertEqual(req.frozen_cost_rate, 300.0)
		self.assertEqual(req.cost_locked, 1)

	def test_14_freeze_zero_when_no_cost(self):
		# Required Item comprable pero sin ninguna fuente → congelar 0 / sin_costo / locked.
		code = "_Test RI NoCost"
		if not frappe.db.exists("Item", code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": code,
					"item_group": get_test_item_group(),
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"is_sales_item": 0,
					"is_purchase_item": 1,
				}
			).insert(ignore_permissions=True)
		# Item vendido con ingreso (la transición exige venta neta > 0); el Required Item sin costo congela 0.
		q = self._make_quotation(sold=[IT_RESALE], required=[code])
		doc = self._transition(frappe.get_doc("Quotation", q.name))
		req = next(r for r in doc.get("required_items") if r.item == code)
		self.assertEqual(req.frozen_cost_rate, 0.0)
		self.assertEqual(req.frozen_cost_source, "sin_costo")
		self.assertEqual(req.cost_locked, 1)

	def test_15_item_price_change_after_freeze_no_effect(self):
		q = self._make_quotation(sold=[IT_RESALE])
		doc = self._transition(frappe.get_doc("Quotation", q.name))
		before = self._profit(doc.name)["totals"]["item_cost"]
		self.assertEqual(before, 300.0)
		# cambiar el Item Price después del freeze
		ip = frappe.db.get_value("Item Price", {"item_code": IT_RESALE, "price_list": BPL}, "name")
		frappe.db.set_value("Item Price", ip, "price_list_rate", 900)
		after = self._profit(doc.name)["totals"]["item_cost"]
		frappe.db.set_value("Item Price", ip, "price_list_rate", 300)  # restaurar
		self.assertEqual(after, 300.0)  # histórico congelado, no cambia

	# ─────────────────────────── Project / Tasks ────────────────────────────

	def test_21_project_from_required_item_scope(self):
		from erpnext_proposals.erpnext_proposals.utils.project import create_project_from_quotation

		q = self._make_quotation(sold=[IT_RESALE], required=[IT_REQ_BUY])
		doc = self._transition(frappe.get_doc("Quotation", q.name))
		apply_workflow(doc, _action(doc, "En Revision", "Aprobada"))
		doc.reload()
		apply_workflow(doc, _action(doc, "Aprobada", "Enviada al Cliente"))
		doc.reload()
		apply_workflow(doc, _action(doc, "Enviada al Cliente", "Ganada"))
		create_project_from_quotation(q.name)
		project = frappe.db.get_value("Quotation", q.name, "proposal_project")
		self.assertTrue(project)
		# Existe al menos una Task originada en un scope de Required Item.
		req_scope_rows = [
			r.name
			for r in frappe.get_doc("Quotation", q.name).quotation_scope_items
			if r.item_code == IT_REQ_BUY
		]
		tasks = frappe.get_all(
			"Task", {"project": project, "source_quotation_scope_item": ["in", req_scope_rows]}
		)
		self.assertTrue(tasks)


def flt_first(rows):
	return rows[0]


def _action(doc, state, next_state):
	wf = frappe.db.get_value("Workflow", {"document_type": "Quotation", "is_active": 1}, "name")
	return frappe.db.get_value(
		"Workflow Transition", {"parent": wf, "state": state, "next_state": next_state}, "action"
	)


if __name__ == "__main__":
	unittest.main()
