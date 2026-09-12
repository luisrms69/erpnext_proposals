"""Tests — contrato económico canónico Project ↔ Quotations (`utils/project_economics.py`).

Prueba el CONTRATO (resolución, agregación, guards, sync), no reimplementa las fórmulas del motor.
Autorizado = Original (root) + Σ(addendas aplicadas), por magnitud independiente; `margin_pct` derivado;
financiamiento excluido; fail-closed ante snapshot incompleto, moneda incompatible o root no única.
"""

import unittest

import frappe
from frappe.exceptions import ValidationError
from frappe.utils import flt, today

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
from erpnext_proposals.erpnext_proposals.tests.phases import cleanup_test_phases, ensure_test_phases
from erpnext_proposals.erpnext_proposals.utils import project_economics as pe
from erpnext_proposals.erpnext_proposals.utils.project_economics import (
	get_project_authorized_economics,
	sync_project_authorized_cost,
)

ITEM = "_ZZPE Item"
CUST = "_ZZPE Cust"
TEMPLATE = "_ZZPE Template"


class TestProjectEconomics(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._q, cls._p = [], []
		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company on test site.")
		cls._phases = ensure_test_phases()
		cls._fy = ensure_current_fiscal_year()
		cls.price_list = get_test_price_list()
		cls.cc = get_test_cost_center(cls.company)
		ig = get_test_item_group()
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {}, "name")
		if not cg:
			raise unittest.SkipTest("No Customer Group on test site.")
		if not frappe.db.exists("Customer", CUST):
			frappe.get_doc(
				{"doctype": "Customer", "customer_name": CUST, "customer_group": cg, "territory": terr}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": ITEM,
					"item_group": ig,
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"is_sales_item": 1,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "t"}
			).insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		if frappe.db.exists("Proposal Template", TEMPLATE):
			try:
				frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
			except Exception:
				pass
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
		cleanup_test_phases(getattr(cls, "_phases", None))
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		super().tearDownClass()

	# ── Helpers ──────────────────────────────────────────────────────────────
	def _project(self):
		p = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": "ZZPE-" + frappe.generate_hash(length=6),
				"company": self.company,
				"status": "Open",
			}
		)
		p.insert(ignore_permissions=True)
		self.__class__._p.append(p.name)
		return p.name

	def _frozen_q(self, group, sold, labor, project=None, addendum=False, ganada=True):
		"""Quotation con economía CONGELADA a mano (rate_locked/proposal_cost_locked/behavior), sin template.

		sold: [(sell_rate, qty, ext_rate)] · labor: [(hours, costing_rate)]. Los rows ya vienen locked, así
		que el freeze de `before_submit` es no-op y `assert_economic_snapshot_complete` pasa."""
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": CUST,
				"company": self.company,
				"currency": "MXN",
				"selling_price_list": self.price_list,
				"transaction_date": today(),
				"proposal_group": group,
				"proposal_cost_center": self.cc,
				"proposal_title": group,
				"proposal_contract_term_months": 12,
				"items": [
					{
						"item_code": ITEM,
						"item_name": ITEM,
						"qty": q,
						"rate": r,
						"uom": "Nos",
						"proposal_cost_locked": 1,
						"proposal_frozen_cost_rate": ext,
						"proposal_frozen_cost_source": "frozen",
						"proposal_economic_behavior": "one_time",
						"proposal_billing_interval": "",
						"proposal_billing_interval_count": 0,
					}
					for (r, q, ext) in sold
				],
			}
		)
		for i, (hours, rate) in enumerate(labor, 1):
			doc.append(
				"quotation_scope_items",
				{
					"code": f"{group}-S{i}",
					"title": f"S{i}",
					"phase": "DISC",
					"sequence": i,
					"item_code": ITEM,
					"estimated_hours": hours,
					"include_in_proposal": 1,
					"rate_locked": 1,
					"costing_rate": rate,
					"rate_source": "ZZ-TEST",
				},
			)
		if addendum:
			doc.flags.from_addendum_creation = True
		doc.flags.skip_scope_generation = True
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._q.append(doc.name)
		if ganada:
			doc.reload()
			doc.flags.ignore_mandatory = True
			doc.flags.ignore_links = True
			doc.submit()
			frappe.db.set_value("Quotation", doc.name, "workflow_state", "Ganada", update_modified=False)
		# Marca como propuesta FORMAL (con template) DESPUÉS del submit: no regenera scope y activa el guard
		# de snapshot en el contrato económico (una propuesta real siempre tiene template).
		frappe.db.set_value("Quotation", doc.name, "proposal_template", TEMPLATE, update_modified=False)
		if project:
			frappe.db.set_value("Quotation", doc.name, "proposal_project", project, update_modified=False)
		return doc.name

	def _root_with(self, project, sold=((1000, 1, 100),), labor=((10, 50),)):
		grp = "ZZPE-ROOT-" + frappe.generate_hash(length=6)
		self._frozen_q(grp, list(sold), list(labor), project=project)
		return grp

	# ── Contrato: agregación ───────────────────────────────────────────────────
	def test_root_only(self):
		proj = self._project()
		self._root_with(proj, sold=[(1000, 1, 100)], labor=[(10, 50)])
		e = get_project_authorized_economics(proj)
		# revenue 1000, external 100, labor 500 -> cost 600, margin 400
		self.assertEqual(e["authorized_revenue"], 1000.0)
		self.assertEqual(e["authorized_external"], 100.0)
		self.assertEqual(e["authorized_labor"], 500.0)
		self.assertEqual(e["authorized_cost"], 600.0)
		self.assertEqual(e["authorized_margin"], 400.0)
		self.assertEqual(e["applied_changes_cost"], 0.0)
		self.assertEqual(e["original_cost"], 600.0)

	def test_root_plus_one_addendum(self):
		proj = self._project()
		root_g = self._root_with(proj, sold=[(1000, 1, 100)], labor=[(10, 50)])
		self._frozen_q(f"{root_g}-ADD-01", [(300, 1, 0)], [(4, 50)], project=proj, addendum=True)
		e = get_project_authorized_economics(proj)
		# original: rev1000/ext100/lab500/cost600/mar400 ; add01: rev300/lab200/cost200/mar100
		self.assertEqual(e["original_revenue"], 1000.0)
		self.assertEqual(e["applied_changes_revenue"], 300.0)
		self.assertEqual(e["authorized_revenue"], 1300.0)
		self.assertEqual(e["authorized_labor"], 700.0)
		self.assertEqual(e["authorized_external"], 100.0)
		self.assertEqual(e["authorized_cost"], 800.0)
		self.assertEqual(e["authorized_margin"], 500.0)

	def test_root_plus_multiple_addenda(self):
		proj = self._project()
		root_g = self._root_with(proj, sold=[(1000, 1, 0)], labor=[(10, 50)])
		self._frozen_q(f"{root_g}-ADD-01", [(300, 1, 0)], [(4, 50)], project=proj, addendum=True)
		self._frozen_q(f"{root_g}-ADD-02", [(200, 1, 0)], [(2, 50)], project=proj, addendum=True)
		e = get_project_authorized_economics(proj)
		self.assertEqual(e["authorized_revenue"], 1500.0)  # 1000+300+200
		self.assertEqual(e["authorized_labor"], 800.0)  # 500+200+100
		self.assertEqual(e["applied_changes_labor"], 300.0)
		self.assertEqual(len(e["quotations"]), 3)

	def test_pending_addendum_not_summed(self):
		proj = self._project()
		root_g = self._root_with(proj, sold=[(1000, 1, 0)], labor=[(10, 50)])
		# Addenda Ganada del mismo root pero NO aplicada a este project (sin proposal_project==proj):
		pend = self._frozen_q(f"{root_g}-ADD-01", [(999, 1, 0)], [(9, 50)], project=None, addendum=True)
		e = get_project_authorized_economics(proj)
		self.assertEqual(e["authorized_revenue"], 1000.0, "el pendiente no suma")
		self.assertIn(pend, e["pending_changes"])
		self.assertEqual([q["name"] for q in e["quotations"]], [e["root_quotation"]])

	def test_superseded_not_summed(self):
		proj = self._project()
		root_g = self._root_with(proj, sold=[(1000, 1, 0)], labor=[(10, 50)])
		add = self._frozen_q(f"{root_g}-ADD-01", [(300, 1, 0)], [(4, 50)], project=proj, addendum=True)
		# Marcar la addenda como superseded (Link a sí misma como placeholder) -> excluida.
		frappe.db.set_value("Quotation", add, "superseded_by_proposal", add, update_modified=False)
		e = get_project_authorized_economics(proj)
		self.assertEqual(e["authorized_revenue"], 1000.0, "una addenda superseded no suma")
		self.assertNotIn(add, [q["name"] for q in e["quotations"]])

	def test_each_quotation_appears_once(self):
		proj = self._project()
		root_g = self._root_with(proj, labor=[(10, 50)])
		a1 = self._frozen_q(f"{root_g}-ADD-01", [(300, 1, 0)], [(4, 50)], project=proj, addendum=True)
		a2 = self._frozen_q(f"{root_g}-ADD-02", [(200, 1, 0)], [(2, 50)], project=proj, addendum=True)
		names = [q["name"] for q in get_project_authorized_economics(proj)["quotations"]]
		self.assertEqual(len(names), len(set(names)))
		self.assertEqual(set(names), {get_project_authorized_economics(proj)["root_quotation"], a1, a2})

	# ── Financiamiento / margin_pct ────────────────────────────────────────────
	def test_financing_excluded_and_cost_is_labor_plus_external(self):
		proj = self._project()
		self._root_with(proj, sold=[(1000, 1, 100)], labor=[(10, 50)])
		e = get_project_authorized_economics(proj)
		self.assertTrue(e["financing_excluded"])
		self.assertEqual(e["authorized_cost"], e["authorized_labor"] + e["authorized_external"])

	def test_margin_pct_derived_not_summed(self):
		proj = self._project()
		root_g = self._root_with(proj, sold=[(1000, 1, 0)], labor=[(10, 50)])
		self._frozen_q(f"{root_g}-ADD-01", [(300, 1, 0)], [(4, 50)], project=proj, addendum=True)
		e = get_project_authorized_economics(proj)
		expected = e["authorized_margin"] / e["authorized_revenue"] * 100.0
		self.assertAlmostEqual(e["authorized_margin_pct"], expected, places=6)

	# ── Moneda ─────────────────────────────────────────────────────────────────
	def test_currency_consistent_true(self):
		proj = self._project()
		self._root_with(proj)
		self.assertTrue(get_project_authorized_economics(proj)["currency_consistent"])

	def test_currency_incompatible_blocks(self):
		proj = self._project()
		root_g = self._root_with(proj)
		root = frappe.get_all("Quotation", filters={"proposal_group": root_g}, pluck="name")[0]
		frappe.db.set_value("Quotation", root, "currency", "USD", update_modified=False)
		with self.assertRaises(ValidationError):
			get_project_authorized_economics(proj)

	def test_conversion_rate_incompatible_blocks(self):
		proj = self._project()
		root_g = self._root_with(proj)
		root = frappe.get_all("Quotation", filters={"proposal_group": root_g}, pluck="name")[0]
		frappe.db.set_value("Quotation", root, "conversion_rate", 1.5, update_modified=False)
		with self.assertRaises(ValidationError):
			get_project_authorized_economics(proj)

	# ── Fail-closed: snapshot / root ───────────────────────────────────────────
	def test_snapshot_incomplete_blocks(self):
		proj = self._project()
		root_g = self._root_with(proj, labor=[(10, 50)])
		root = frappe.get_all("Quotation", filters={"proposal_group": root_g}, pluck="name")[0]
		child = frappe.get_all("Quotation Scope Item", filters={"parent": root}, pluck="name")[0]
		# Corromper el snapshot (escritura directa privilegiada): fila costable sin rate_locked.
		frappe.db.set_value("Quotation Scope Item", child, "rate_locked", 0, update_modified=False)
		with self.assertRaises(ValidationError):
			get_project_authorized_economics(proj)

	def test_zero_root_blocks(self):
		proj = self._project()  # sin ninguna Quotation asociada
		with self.assertRaises(ValidationError):
			get_project_authorized_economics(proj)

	def test_multiple_roots_block(self):
		proj = self._project()
		self._root_with(proj)  # root 1 (grupo normal)
		self._root_with(proj)  # root 2 (grupo normal) -> 2 raíces normales
		with self.assertRaises(ValidationError):
			get_project_authorized_economics(proj)

	def test_rate_locked_zero_stays_zero(self):
		proj = self._project()
		# rate_locked=1 con costing_rate=0 -> labor 0, sin reconsultar Cost Matrix.
		self._root_with(proj, sold=[(1000, 1, 0)], labor=[(10, 0)])
		e = get_project_authorized_economics(proj)
		self.assertEqual(e["authorized_labor"], 0.0)
		self.assertEqual(e["authorized_cost"], 0.0)

	# ── Sync a Project.estimated_costing ───────────────────────────────────────
	def test_sync_sets_estimated_costing_and_idempotent(self):
		proj = self._project()
		self._root_with(proj, sold=[(1000, 1, 100)], labor=[(10, 50)])
		econ = sync_project_authorized_cost(proj)
		self.assertEqual(econ["authorized_cost"], 600.0)
		self.assertEqual(flt(frappe.db.get_value("Project", proj, "estimated_costing")), 600.0)
		# Idempotente: reejecutar no cambia el valor.
		sync_project_authorized_cost(proj)
		self.assertEqual(flt(frappe.db.get_value("Project", proj, "estimated_costing")), 600.0)

	def test_manual_edit_corrected_on_next_sync(self):
		proj = self._project()
		self._root_with(proj, sold=[(1000, 1, 100)], labor=[(10, 50)])
		sync_project_authorized_cost(proj)
		frappe.db.set_value("Project", proj, "estimated_costing", 99999.0, update_modified=False)
		sync_project_authorized_cost(proj)
		self.assertEqual(flt(frappe.db.get_value("Project", proj, "estimated_costing")), 600.0)

	def test_economic_failure_propagates(self):
		proj = self._project()
		self._root_with(proj)
		orig = pe._evaluate_doc

		def _boom(*a, **k):
			raise RuntimeError("boom económico")

		pe._evaluate_doc = _boom
		try:
			with self.assertRaises(RuntimeError):
				sync_project_authorized_cost(proj)
		finally:
			pe._evaluate_doc = orig


if __name__ == "__main__":
	unittest.main()
