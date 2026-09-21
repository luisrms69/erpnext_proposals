"""HOTFIX — reparación canónica de snapshots económicos LEGACY.

Casos: 1 legacy submitted totalmente faltante → se repara · 2 snapshot existente → nunca se sobrescribe ·
3 parcial/ambiguo → aborta · 4 Scope costable sin rate_locked → aborta · 5 tras reparar el guard pasa ·
6 propuesta nueva no cambia · 7 idempotencia (segunda corrida = 0 cambios).
"""

import unittest

import frappe
from frappe.utils import flt

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.tests.phases import cleanup_test_phases, ensure_test_phases
from erpnext_proposals.erpnext_proposals.utils.legacy_repair import (
	legacy_cutoff,
	repair_legacy_economic_snapshot,
)
from erpnext_proposals.erpnext_proposals.utils.quotation import assert_economic_snapshot_complete

SECTION = "_LR Section"
SCOPE = "_LR_SCOPE"
TPL = "_LR Template"


class TestLegacyEconomicRepair(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from erpnext_proposals.erpnext_proposals.tests.company import (
			get_test_company,
			get_test_cost_center,
		)

		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company on test site.")
		cls._fy = ensure_current_fiscal_year()
		cls._phases = ensure_test_phases()
		cls.item = _ensure_item()
		cls.customer = _ensure_customer()
		cls.cost_center = get_test_cost_center(cls.company)

		if not frappe.db.exists("Proposal Section", SECTION):
			frappe.get_doc(
				{
					"doctype": "Proposal Section",
					"section_name": SECTION,
					"title": "S",
					"content": "<p>x</p>",
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Scope Item", SCOPE):
			frappe.get_doc(
				{
					"doctype": "Scope Item",
					"code": SCOPE,
					"title": "Act",
					"sequence": 10,
					"phase": "DISC",
					"estimated_hours": 4,
					"erpnext_item": cls.item,
					"enabled": 1,
					"visible_in_proposal": 1,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TPL):
			t = frappe.get_doc({"doctype": "Proposal Template", "template_name": TPL})
			t.append("sections", {"proposal_section": SECTION, "sequence": 10, "include_by_default": 1})
			t.insert(ignore_permissions=True)
		frappe.db.commit()  # nosemgrep — aislamiento de test

	@classmethod
	def tearDownClass(cls):
		cleanup_test_phases(getattr(cls, "_phases", None))
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		super().tearDownClass()

	# ── helpers ──────────────────────────────────────────────────────────────
	def _submit(self):
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_price_list

		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": f"LR-{frappe.generate_hash(length=6)}",
				"proposal_template": TPL,
				"proposal_title": "LR Test",
				"proposal_cost_center": self.cost_center,
				"selling_price_list": get_test_price_list(),
				"items": [{"item_code": self.item, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		doc.reload()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		doc.reload()
		return doc

	def _strip_item_econ(self, doc):
		"""Simula una Quotation LEGACY: vacía el snapshot económico de las líneas vendidas (db_set en
		submitted), dejando intactos los Scope Items (rate_locked)."""
		for it in doc.items:
			it.db_set("proposal_cost_locked", 0, update_modified=False)
			it.db_set("proposal_economic_behavior", "", update_modified=False)
			it.db_set("proposal_frozen_cost_rate", 0, update_modified=False)
			it.db_set("proposal_frozen_cost_source", "", update_modified=False)
			it.db_set("proposal_billing_interval", "", update_modified=False)
			it.db_set("proposal_billing_interval_count", 0, update_modified=False)
		frappe.db.commit()  # nosemgrep — aislamiento de test
		doc.reload()

	def _make_legacy(self, doc):
		"""Fija creation ANTES del cutoff del modelo económico → Quotation demostrablemente pre-modelo."""
		from frappe.utils import add_to_date, get_datetime

		cutoff, _f = legacy_cutoff()
		self.assertTrue(cutoff, "el site debe tener los Custom Fields del modelo económico")
		doc.db_set("creation", add_to_date(get_datetime(cutoff), days=-1), update_modified=False)
		frappe.db.commit()  # nosemgrep — aislamiento de test
		doc.reload()

	# ── casos ────────────────────────────────────────────────────────────────
	def test_1_legacy_fully_missing_repaired(self):
		q = self._submit()
		try:
			self._strip_item_econ(q)
			self._make_legacy(q)  # creation anterior al cutoff → elegible
			# antes: el guard falla
			with self.assertRaises(frappe.ValidationError):
				assert_economic_snapshot_complete(frappe.get_doc("Quotation", q.name))
			rep = repair_legacy_economic_snapshot(q.name, dry_run=False)
			self.assertTrue(rep["applied"])
			self.assertTrue(rep["legacy_eligible"])
			self.assertIsNotNone(rep["legacy_cutoff"])
			self.assertIn("creation", rep)
			self.assertIn("workflow_state", rep)
			self.assertEqual(rep["guard_after"], "ok")
			self.assertEqual(len(rep["items_to_repair"]), 1)
			fresh = frappe.get_doc("Quotation", q.name)
			it = fresh.items[0]
			self.assertEqual(it.proposal_cost_locked, 1)
			self.assertEqual(it.proposal_economic_behavior, "one_time")
			self.assertEqual(it.proposal_frozen_cost_source, "legacy_pre_economic_model")
			self.assertEqual(flt(it.proposal_frozen_cost_rate), 0)
			# test 5: guard pasa tras reparar
			assert_economic_snapshot_complete(fresh)  # no raise
		finally:
			_cancel_delete(q.name)

	def test_1b_post_cutoff_empty_aborts(self):
		# snapshot vacío pero creation POSTERIOR al cutoff → NO legacy → posible corrupción → aborta
		q = self._submit()
		try:
			self._strip_item_econ(q)  # vacío, pero SIN _make_legacy → creation = ahora (> cutoff)
			rep = repair_legacy_economic_snapshot(q.name, dry_run=False)
			self.assertFalse(rep["applied"])
			self.assertFalse(rep["legacy_eligible"])
			self.assertTrue(any(("CORRUPCIÓN" in b) or ("NO elegible" in b) for b in rep["blockers"]))
			# no persistió: sigue vacío
			self.assertEqual(frappe.get_doc("Quotation", q.name).items[0].proposal_cost_locked, 0)
		finally:
			_cancel_delete(q.name)

	def test_2_existing_snapshot_never_overwritten(self):
		q = self._submit()
		try:
			before = frappe.get_doc("Quotation", q.name).items[0].proposal_economic_behavior
			rep = repair_legacy_economic_snapshot(q.name, dry_run=False)
			self.assertTrue(rep["already_complete"])
			self.assertFalse(rep["applied"])
			self.assertEqual(rep["items_to_repair"], [])
			after = frappe.get_doc("Quotation", q.name).items[0].proposal_economic_behavior
			self.assertEqual(before, after)  # no sobrescribe
		finally:
			_cancel_delete(q.name)

	def test_3_partial_ambiguous_aborts(self):
		q = self._submit()
		try:
			# parcial: quita SOLO el behavior; deja cost_locked=1 → ambiguo
			q.items[0].db_set("proposal_economic_behavior", "", update_modified=False)
			frappe.db.commit()  # nosemgrep — aislamiento de test
			rep = repair_legacy_economic_snapshot(q.name, dry_run=True)
			self.assertFalse(rep["applied"])
			self.assertTrue(any("PARCIAL" in b for b in rep["blockers"]))
			self.assertEqual(rep["items_to_repair"], [])
		finally:
			_cancel_delete(q.name)

	def test_4_scope_without_rate_locked_aborts(self):
		q = self._submit()
		try:
			self._strip_item_econ(q)  # hay algo que reparar en items
			self._make_legacy(q)  # elegible → así el ÚNICO blocker es el de scope
			# rompe un scope costable: quita rate_locked
			fresh = frappe.get_doc("Quotation", q.name)
			costable = [
				s for s in fresh.quotation_scope_items if s.include_in_proposal or s.is_internal_cost_task
			]
			self.assertTrue(costable, "el fixture debe tener un scope costable")
			costable[0].db_set("rate_locked", 0, update_modified=False)
			frappe.db.commit()  # nosemgrep — aislamiento de test
			rep = repair_legacy_economic_snapshot(q.name, dry_run=False)
			self.assertFalse(rep["applied"])
			self.assertTrue(any("rate_locked" in b for b in rep["blockers"]))
			# no persistió nada: los items siguen sin snapshot
			self.assertEqual(frappe.get_doc("Quotation", q.name).items[0].proposal_cost_locked, 0)
		finally:
			_cancel_delete(q.name)

	def test_6_new_proposal_unchanged(self):
		q = self._submit()
		try:
			rep = repair_legacy_economic_snapshot(q.name, dry_run=True)
			self.assertTrue(rep["already_complete"])
			self.assertEqual(rep["items_to_repair"], [])
			self.assertEqual(rep["required_to_repair"], [])
		finally:
			_cancel_delete(q.name)

	def test_7_idempotent_second_run(self):
		q = self._submit()
		try:
			self._strip_item_econ(q)
			self._make_legacy(q)
			r1 = repair_legacy_economic_snapshot(q.name, dry_run=False)
			self.assertTrue(r1["applied"])
			r2 = repair_legacy_economic_snapshot(q.name, dry_run=False)
			self.assertFalse(r2["applied"])
			self.assertTrue(r2["already_complete"])
			self.assertEqual(r2["items_to_repair"], [])
		finally:
			_cancel_delete(q.name)

	def test_precondition_fails_closed(self):
		# no existe
		with self.assertRaises(frappe.ValidationError):
			repair_legacy_economic_snapshot("_LR_NO_EXISTE_999", dry_run=True)


def _ensure_item():
	name = "_LR Item"
	if not frappe.db.exists("UOM", "Nos"):
		frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
	if not frappe.db.exists("Item", name):
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_item_group

		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": name,
				"item_name": name,
				"item_group": get_test_item_group(),
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)
	return name


def _ensure_customer():
	name = "_LR Customer"
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_type": "Company",
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
				"territory": frappe.db.get_value("Territory", {}, "name"),
			}
		).insert(ignore_permissions=True)
	return name


def _cancel_delete(name):
	if not frappe.db.exists("Quotation", name):
		return
	try:
		q = frappe.get_doc("Quotation", name)
		if q.docstatus == 1:
			q.flags.ignore_linked_doctypes = True
			q.cancel()
		frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
	except Exception:
		pass
