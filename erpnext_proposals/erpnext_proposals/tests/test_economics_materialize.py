# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Economía materializada en la Quotation (B7 / ADR-0022).

Los valores económicos (costo externo + comportamiento) se resuelven y persisten en las filas durante
Draft; ``docstatus=1`` los congela. El freeze ya no recalcula ni bloquea, y NO se requieren flags de
lock para formalizar. Un cambio posterior en los masters no altera un Draft existente (solo el resync
explícito). Sin datos de cliente.
"""

import unittest

import frappe

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
from erpnext_proposals.erpnext_proposals.utils.quotation import assert_economic_snapshot_complete

TEMPLATE = "_Test Econ Template"
ITEM = "_Test Econ Item"
CUSTOMER = "_Test Econ Customer"

_IMMUTABLE_EXCEPTIONS = (
	frappe.exceptions.ValidationError,
	frappe.exceptions.UpdateAfterSubmitError,
)


class TestEconomicsMaterialize(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		cls._fy = ensure_current_fiscal_year()
		cls._phases = ensure_test_phases()
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or frappe.db.get_value(
			"Territory", {}, "name"
		)
		if not frappe.db.exists("Customer", CUSTOMER):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": CUSTOMER,
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		ig = get_test_item_group()
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": ITEM,
					"item_group": ig,
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc({"doctype": "Proposal Template", "template_name": TEMPLATE}).insert(
				ignore_permissions=True
			)
		cls.cost_center = get_test_cost_center(cls.company)
		cls._quotations = []

	@classmethod
	def tearDownClass(cls):
		for n in cls._quotations:
			if frappe.db.exists("Quotation", n):
				try:
					q = frappe.get_doc("Quotation", n)
					if q.docstatus == 1:
						q.flags.ignore_linked_doctypes = True
						q.cancel()
					frappe.delete_doc("Quotation", n, force=True, ignore_permissions=True)
				except Exception:
					pass
		cleanup_test_phases(getattr(cls, "_phases", None))
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		super().tearDownClass()

	def _make_draft(self):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": CUSTOMER,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": f"ECON-{frappe.generate_hash(length=8)}",
				"proposal_template": TEMPLATE,
				"proposal_title": "Econ",
				"proposal_cost_center": self.cost_center,
				"selling_price_list": get_test_price_list(),
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self._quotations.append(doc.name)
		return frappe.get_doc("Quotation", doc.name)

	# ── en Draft ya existen los valores materializados, sin flags de lock ───────

	def test_01_draft_materializes_item_economics(self):
		doc = self._make_draft()
		self.assertEqual(doc.docstatus, 0, "sigue en Draft")
		it = doc.items[0]
		self.assertTrue(it.get("proposal_frozen_cost_source"), "costo externo materializado en Draft")
		self.assertTrue(it.get("proposal_economic_behavior"), "comportamiento materializado en Draft")
		# el flujo nuevo NO escribe flags de lock
		self.assertFalse(it.get("proposal_cost_locked"), "no se escribe proposal_cost_locked")

	# ── no se requieren locks para formalizar ───────────────────────────────────

	def test_02_submit_without_locks(self):
		doc = self._make_draft()
		# el gate económico pasa con los valores materializados (sin locks)
		assert_economic_snapshot_complete(doc)
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		fresh = frappe.get_doc("Quotation", doc.name)
		self.assertEqual(fresh.docstatus, 1)
		self.assertTrue(fresh.items[0].get("proposal_frozen_cost_source"))
		self.assertFalse(fresh.items[0].get("proposal_cost_locked"), "formaliza sin flag de lock")

	# ── submit no recalcula: el valor materializado en Draft persiste ───────────

	def test_03_submit_does_not_recompute(self):
		doc = self._make_draft()
		before_rate = doc.items[0].get("proposal_frozen_cost_rate")
		before_src = doc.items[0].get("proposal_frozen_cost_source")
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		it = frappe.get_doc("Quotation", doc.name).items[0]
		self.assertEqual(it.get("proposal_frozen_cost_rate"), before_rate, "el submit no recalcula el costo")
		self.assertEqual(it.get("proposal_frozen_cost_source"), before_src)

	# ── submitted inmutable por docstatus ───────────────────────────────────────

	def test_04_submitted_economics_immutable(self):
		doc = self._make_draft()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		fresh = frappe.get_doc("Quotation", doc.name)
		fresh.items[0].proposal_frozen_cost_rate = 99999
		with self.assertRaises(_IMMUTABLE_EXCEPTIONS):
			fresh.save()
