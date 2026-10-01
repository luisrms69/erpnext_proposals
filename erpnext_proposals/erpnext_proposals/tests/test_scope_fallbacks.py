# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Fallbacks de alcance (Iniciativa 3): un Item vendido SIN Scope propio genera una Task de **compromiso**
por ocurrencia (``default_commitment_scope_item``), y cada ocurrencia **comprable aplicable** (vendida o
requerida) genera una Task individual de **compra** (``default_purchase_scope_item``), todo por la ruta
única Item→Scope→Phase→Quotation Scope Item→Task, con identidad ``(source_row, scope_item)``. Datos ficticios.
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
IT_SIMPLE = "_FB Simple"  # vendido NO comprable, SIN scope → compromiso
IT_HW = "_FB Hardware"  # vendido comprable SIN scope → compromiso + compra
IT_REQ_BUY = "_FB ReqBuy"  # requerido comprable → compra
IT_SKIP = "_FB Skip"  # vendido comprable con skip → sin compra

OWN_SCOPE = "_FB_OWN"  # scope propio de IT_SVC_SCOPED
COMMIT_SCOPE = "_FB_COMMIT"  # fallback compromiso
PURCH_SCOPE = "_FB_PURCH"  # fallback compra


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

		def _item(code, sales, purchase, skip=0):
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
			if skip:
				frappe.db.set_value("Item", code, "proposal_skip_procurement", 1)

		for c, s, p, sk in [
			(IT_SVC_SCOPED, 1, 0, 0),
			(IT_SIMPLE, 1, 0, 0),
			(IT_HW, 1, 1, 0),
			(IT_REQ_BUY, 0, 1, 0),
			(IT_SKIP, 1, 1, 1),
		]:
			_item(c, s, p, sk)

		# Scope propio de IT_SVC_SCOPED (asociación legacy erpnext_item).
		cls._scope(OWN_SCOPE, IT_SVC_SCOPED, hours=5, visible=1, internal=0)
		# Fallbacks: hrs 0 (recomendado). Compromiso visible; compra interna (no cliente).
		cls._scope(COMMIT_SCOPE, None, hours=0, visible=1, internal=0)
		cls._scope(PURCH_SCOPE, None, hours=0, visible=0, internal=1)
		cls._set_settings(commitment=COMMIT_SCOPE, purchase=PURCH_SCOPE)
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
		name = frappe.db.get_value("Proposal Settings", {"company": get_test_company()}, "name")
		if name:
			frappe.delete_doc("Proposal Settings", name, force=True, ignore_permissions=True)
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

	@classmethod
	def _set_settings(cls, commitment=None, purchase=None):
		company = get_test_company()
		name = frappe.db.get_value("Proposal Settings", {"company": company}, "name")
		s = frappe.get_doc("Proposal Settings", name) if name else frappe.new_doc("Proposal Settings")
		s.company = company
		s.default_commitment_scope_item = commitment
		s.default_purchase_scope_item = purchase
		s.flags.ignore_permissions = True
		s.save(ignore_permissions=True)

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
	def test_01_sold_without_scope_gets_commitment(self):
		q = self._quotation(
			[{"item_code": IT_SIMPLE, "item_name": IT_SIMPLE, "qty": 1, "rate": 1000, "uom": "Nos"}]
		)
		rows = self._scope_rows(q)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0][2], COMMIT_SCOPE)

	def test_02_sold_with_scope_no_commitment(self):
		q = self._quotation(
			[{"item_code": IT_SVC_SCOPED, "item_name": IT_SVC_SCOPED, "qty": 1, "rate": 1000, "uom": "Nos"}]
		)
		codes = [r[2] for r in self._scope_rows(q)]
		self.assertIn(OWN_SCOPE, codes)
		self.assertNotIn(COMMIT_SCOPE, codes)

	def test_03_three_simple_items_three_commitments(self):
		with change_settings("Selling Settings", {"allow_multiple_items": 1}):
			q = self._quotation(
				[
					{"item_code": IT_SIMPLE, "item_name": IT_SIMPLE, "qty": 1, "rate": 1000, "uom": "Nos"}
					for _ in range(3)
				]
			)
		commit = [r for r in self._scope_rows(q) if r[2] == COMMIT_SCOPE]
		self.assertEqual(len(commit), 3)
		self.assertEqual(len({r[1] for r in commit}), 3)  # tres source_row distintas

	def test_04_purchasable_sold_gets_commitment_and_purchase(self):
		q = self._quotation([{"item_code": IT_HW, "item_name": IT_HW, "qty": 2, "rate": 1000, "uom": "Nos"}])
		codes = [r[2] for r in self._scope_rows(q)]
		self.assertIn(COMMIT_SCOPE, codes)  # sin scope propio → compromiso
		self.assertIn(PURCH_SCOPE, codes)  # comprable → compra

	def test_05_required_purchasable_gets_purchase(self):
		q = self._quotation(
			[{"item_code": IT_SVC_SCOPED, "item_name": IT_SVC_SCOPED, "qty": 1, "rate": 1000, "uom": "Nos"}],
			required=[IT_REQ_BUY],
		)
		req = [r for r in self._scope_rows(q) if r[0] == "required" and r[2] == PURCH_SCOPE]
		self.assertEqual(len(req), 1)

	def test_06_skip_has_no_purchase(self):
		q = self._quotation(
			[{"item_code": IT_SKIP, "item_name": IT_SKIP, "qty": 1, "rate": 1000, "uom": "Nos"}]
		)
		codes = [r[2] for r in self._scope_rows(q)]
		self.assertNotIn(PURCH_SCOPE, codes)  # skip → sin compra
		self.assertIn(COMMIT_SCOPE, codes)  # pero sí compromiso (sin scope propio)

	def test_07_purchase_scope_zero_hours_no_cost(self):
		q = self._quotation([{"item_code": IT_HW, "item_name": IT_HW, "qty": 2, "rate": 1000, "uom": "Nos"}])
		ev = get_economic_evaluation(q.name)
		self.assertEqual(ev["totals"]["labor"], 0.0)  # fallbacks hrs 0 → sin costo laboral
		self.assertEqual(ev["totals"]["external"], 0.0)  # sin buying price → sin costo externo

	def test_08_project_tasks_and_subjects(self):
		q = self._quotation([{"item_code": IT_HW, "item_name": IT_HW, "qty": 2, "rate": 1000, "uom": "Nos"}])
		proj = self._win_project(q)
		subs = self._subjects(proj)
		self.assertTrue(any(s.startswith("Entregar — ") for s in subs), subs)
		self.assertTrue(any(s.startswith("Comprar — ") and "× 2" in s for s in subs), subs)  # noqa: RUF001

	def test_09_idempotent_retry_no_duplicate(self):
		q = self._quotation([{"item_code": IT_HW, "item_name": IT_HW, "qty": 2, "rate": 1000, "uom": "Nos"}])
		proj = self._win_project(q)
		n1 = len(self._subjects(proj))
		create_project_from_quotation(q.name)  # reintento
		self.assertEqual(len(self._subjects(proj)), n1)

	def test_10_forward_only_no_settings_no_fallback(self):
		# Sin fallbacks configurados, un Item sin scope no genera QSI (fail-closed lo detecta al crear Project).
		self._set_settings(commitment=None, purchase=None)
		try:
			q = self._quotation(
				[{"item_code": IT_SIMPLE, "item_name": IT_SIMPLE, "qty": 1, "rate": 1000, "uom": "Nos"}]
			)
			self.assertEqual(self._scope_rows(q), [])
		finally:
			self._set_settings(commitment=COMMIT_SCOPE, purchase=PURCH_SCOPE)
