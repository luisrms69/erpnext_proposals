# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Alcance por Item SIN fallbacks de abastecimiento (ADR-0026). El alcance de una ocurrencia es SOLO su
Scope propio (relación N:M). Un Item vendido SIN Scope propio —comprable o no— NO genera Quotation Scope
Item: su seguimiento/cierre es la Task operativa "Entregar — <item>" del padre-Item al crear el Project
(modelo por Item, ADR-0025). Ya NO existe Scope Item de compra por obligación ni paquete de Gestión de
Compras: la compra se gestiona en Buying nativo de ERPNext. Datos ficticios.
"""

import unittest

import frappe
from frappe.tests import change_settings

from erpnext_proposals.erpnext_proposals.tests.company import (
	get_test_company,
	get_test_cost_center,
	get_test_item_group,
	get_test_price_list,
)
from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils.economic_calendar import get_economic_evaluation
from erpnext_proposals.erpnext_proposals.utils.project import create_project_from_quotation

TEMPLATE = "_FB Template"
PHASE = "_FB_PHASE"
ACT = "_FB Activity"

IT_SVC_SCOPED = "_FB Svc Scoped"  # vendido NO comprable, CON scope propio
IT_SIMPLE = "_FB Simple"  # vendido NO comprable, SIN scope → Task operativa
IT_HW = "_FB Hardware"  # vendido COMPRABLE SIN scope → Task operativa (sin compra automática)
IT_REQ_BUY = "_FB ReqBuy"  # requerido comprable SIN scope → sin QSI, sin Task

OWN_SCOPE = "_FB_OWN"  # scope propio de IT_SVC_SCOPED


class TestScopeFallbacks(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._q = []
		cls._p = []
		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company on test site.")
		cls._fy = ensure_current_fiscal_year()
		cls.cc = get_test_cost_center(cls.company)
		cls.price_list = get_test_price_list()
		ig = get_test_item_group()
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {}, "name")
		if not cg:
			raise unittest.SkipTest("No Customer Group on test site.")
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		if not frappe.db.exists("Customer", "_FB Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_FB Customer",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_FB Customer"
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
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "t"}
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

		for c, s, p in [
			(IT_SVC_SCOPED, 1, 0),
			(IT_SIMPLE, 1, 0),
			(IT_HW, 1, 1),
			(IT_REQ_BUY, 0, 1),
		]:
			_item(c, s, p)

		# Scope propio de IT_SVC_SCOPED (asociación legacy erpnext_item).
		cls._scope(OWN_SCOPE, IT_SVC_SCOPED, hours=5, visible=1, internal=0)
		frappe.db.commit()  # nosemgrep — fixtures de test

	@classmethod
	def tearDownClass(cls):
		for p in cls._p:
			for t in frappe.get_all("Task", filters={"project": p}, pluck="name"):
				try:
					frappe.delete_doc("Task", t, force=True, ignore_permissions=True)
				except Exception:
					pass
			if frappe.db.exists("Project", p):
				try:
					frappe.delete_doc("Project", p, force=True, ignore_permissions=True)
				except Exception:
					pass
		for n in cls._q:
			if frappe.db.exists("Quotation", n):
				try:
					d = frappe.get_doc("Quotation", n)
					if d.docstatus == 1:
						d.flags.ignore_linked_doctypes = True
						d.cancel()
					frappe.delete_doc("Quotation", n, force=True, ignore_permissions=True)
				except Exception:
					pass
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_FB_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		frappe.db.commit()  # nosemgrep — limpieza de fixtures de test
		super().tearDownClass()

	# ── helpers ─────────────────────────────────────────────────────────────
	@classmethod
	def _scope(cls, code, item, hours, visible, internal):
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
				"is_internal_cost_task": internal,
				"estimated_hours": hours,
				"default_activity_type": ACT,
				"phase": PHASE,
				"erpnext_item": item,
			}
		).insert(ignore_permissions=True)

	def _quotation(self, item_rows, required=None):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "FB-" + frappe.generate_hash(length=8),
				"company": self.company,
				"currency": "MXN",
				"selling_price_list": self.price_list,
				"transaction_date": frappe.utils.today(),
				"workflow_state": "Borrador",
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cc,
				"proposal_title": "FB " + frappe.generate_hash(length=4),
				"items": item_rows,
				"required_items": [{"item": c, "qty": 1, "uom": "Nos"} for c in (required or [])],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._q.append(doc.name)
		return frappe.get_doc("Quotation", doc.name)

	def _scope_rows(self, doc):
		return [(r.source_type, r.source_row, r.scope_item) for r in doc.quotation_scope_items]

	def _win_project(self, doc):
		doc.reload()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		frappe.db.set_value("Quotation", doc.name, "workflow_state", "Ganada", update_modified=False)
		res = create_project_from_quotation(doc.name)
		self.__class__._p.append(res["project"])
		return res["project"]

	def _subjects(self, project):
		return frappe.get_all("Task", filters={"project": project, "is_group": 0}, pluck="subject")

	# ── tests ───────────────────────────────────────────────────────────────
	def test_01_sold_without_scope_generates_operative_task(self):
		# Un Item vendido sin Scope propio NO genera QSI; su entrega es la Task operativa "Entregar — <item>"
		# del padre-Item en el Project.
		q = self._quotation(
			[{"item_code": IT_SIMPLE, "item_name": IT_SIMPLE, "qty": 1, "rate": 1000, "uom": "Nos"}]
		)
		self.assertEqual(self._scope_rows(q), [], "sin scope propio no se genera QSI")
		proj = self._win_project(q)
		self.assertTrue(
			any(s.startswith("Entregar — ") for s in self._subjects(proj)),
		)

	def test_02_sold_with_scope_only_own(self):
		q = self._quotation(
			[{"item_code": IT_SVC_SCOPED, "item_name": IT_SVC_SCOPED, "qty": 1, "rate": 1000, "uom": "Nos"}]
		)
		codes = [r[2] for r in self._scope_rows(q)]
		self.assertEqual(codes, [OWN_SCOPE], "solo el scope propio N:M")

	def test_03_three_simple_items_three_operative_tasks(self):
		# El submit (dentro de _win_project) debe ir DENTRO del contexto allow_multiple_items=1: 3 ítems
		# idénticos re-validan duplicados en submit y el context manager restaura el valor al salir.
		with change_settings("Selling Settings", {"allow_multiple_items": 1}):
			q = self._quotation(
				[
					{"item_code": IT_SIMPLE, "item_name": IT_SIMPLE, "qty": 1, "rate": 1000, "uom": "Nos"}
					for _ in range(3)
				]
			)
			self.assertEqual(self._scope_rows(q), [], "sin scope propio: 0 QSI")
			proj = self._win_project(q)
		subs = self._subjects(proj)
		# 3 ocurrencias vendidas sin Scope → 3 Task operativas "Entregar —" (una por padre-Item).
		self.assertEqual(sum(1 for s in subs if s.startswith("Entregar — ")), 3, subs)

	def test_04_purchasable_sold_generates_operative_not_purchase(self):
		# Criterio de aceptación v0.36.0 (licencia Microsoft): un Item COMPRABLE vendido sin Scope propio
		# genera SOLO su Task operativa "Entregar — <item>", NO una Task de compra. No hay QSI de compra.
		q = self._quotation([{"item_code": IT_HW, "item_name": IT_HW, "qty": 2, "rate": 1000, "uom": "Nos"}])
		self.assertEqual(
			self._scope_rows(q), [], "comprable sin scope propio: 0 QSI (sin fallback de compra)"
		)
		proj = self._win_project(q)
		subs = self._subjects(proj)
		self.assertTrue(any(s.startswith("Entregar — ") for s in subs), subs)
		self.assertFalse(any(s.startswith("Comprar") for s in subs), f"no debe haber Task de compra: {subs}")

	def test_05_required_purchasable_no_scope_no_task(self):
		# Un Item requerido comprable SIN Scope propio no genera QSI ni Task (los insumos requeridos no crean
		# padre ni Task operativa; solo materializan su propio Scope si lo tienen).
		q = self._quotation(
			[{"item_code": IT_SVC_SCOPED, "item_name": IT_SVC_SCOPED, "qty": 1, "rate": 1000, "uom": "Nos"}],
			required=[IT_REQ_BUY],
		)
		req = [r for r in self._scope_rows(q) if r[0] == "required"]
		self.assertEqual(req, [], "requerido sin scope propio: sin QSI")
		proj = self._win_project(q)
		subs = self._subjects(proj)
		self.assertFalse(any(s.startswith("Comprar") for s in subs), subs)

	def test_06_purchasable_zero_labor_external(self):
		# Un comprable sin Scope propio ni precio de compra no aporta costo: labor 0 (sin horas de scope) y
		# external 0 (sin buying price). La compra se gestiona en Buying nativo, fuera de la propuesta.
		q = self._quotation([{"item_code": IT_HW, "item_name": IT_HW, "qty": 2, "rate": 1000, "uom": "Nos"}])
		ev = get_economic_evaluation(q.name)
		self.assertEqual(ev["totals"]["labor"], 0.0)
		self.assertEqual(ev["totals"]["external"], 0.0)

	def test_07_idempotent_retry_no_duplicate(self):
		q = self._quotation([{"item_code": IT_HW, "item_name": IT_HW, "qty": 2, "rate": 1000, "uom": "Nos"}])
		proj = self._win_project(q)
		n1 = len(self._subjects(proj))
		create_project_from_quotation(q.name)  # reintento
		self.assertEqual(len(self._subjects(proj)), n1)

	def test_08_purchasable_no_config_still_generates(self):
		# Sin ninguna configuración de abastecimiento (ya no existe): un Item comprable vendido sin Scope
		# llega a Ganada y genera su programa (Task operativa), sin bloqueo `sin_compra` (eliminado).
		q = self._quotation([{"item_code": IT_HW, "item_name": IT_HW, "qty": 1, "rate": 1000, "uom": "Nos"}])
		proj = self._win_project(q)
		self.assertTrue(any(s.startswith("Entregar — ") for s in self._subjects(proj)))

	def test_09_operative_task_inherits_project_start_no_end(self):
		# Punto 6: la Task operativa hereda Project.expected_start_date como fecha de INICIO y NO recibe
		# fecha de fin (el PMO la define al planear). La fecha del Project no cambia de origen (ancla).
		q = self._quotation(
			[{"item_code": IT_SIMPLE, "item_name": IT_SIMPLE, "qty": 1, "rate": 1000, "uom": "Nos"}]
		)
		proj = self._win_project(q)
		pstart = frappe.db.get_value("Project", proj, "expected_start_date")
		self.assertTrue(pstart, "el Project tiene fecha de inicio (ancla)")
		rows = frappe.get_all(
			"Task",
			filters={"project": proj, "is_group": 0},
			fields=["subject", "exp_start_date", "exp_end_date"],
		)
		entregar = [t for t in rows if t.subject.startswith("Entregar — ")]
		self.assertTrue(entregar, "hay Task operativa «Entregar»")
		for t in entregar:
			self.assertEqual(
				frappe.utils.getdate(t.exp_start_date),
				frappe.utils.getdate(pstart),
				"inicio de la operativa == ancla del Project",
			)
			self.assertIsNone(t.exp_end_date, "la operativa NO tiene fecha de fin")

	def test_10_create_returns_project_name(self):
		# Punto 3: el retorno de create_project_from_quotation incluye el nombre descriptivo del Project.
		q = self._quotation(
			[{"item_code": IT_SIMPLE, "item_name": IT_SIMPLE, "qty": 1, "rate": 1000, "uom": "Nos"}]
		)
		q.reload()
		q.flags.ignore_mandatory = True
		q.flags.ignore_links = True
		q.submit()
		frappe.db.set_value("Quotation", q.name, "workflow_state", "Ganada", update_modified=False)
		res = create_project_from_quotation(q.name)
		self.__class__._p.append(res["project"])
		self.assertIn("project_name", res)
		self.assertTrue(res["project_name"])
		self.assertEqual(res["project_name"], frappe.db.get_value("Project", res["project"], "project_name"))
