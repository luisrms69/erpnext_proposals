# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Cierre de materialización (B9): SOW PF materializado + fail-closed económico.

- El SOW Print Format se materializa en `proposal_sow_print_format` durante Draft; un submitted no
  relee el Template.
- Los lectores económicos (economic_calendar) son fail-closed en `docstatus=1`: si falta un valor
  materializado, lanzan; nunca hacen fallback silencioso a masters. En Draft sí resuelven en vivo.
Sin datos de cliente.
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
from erpnext_proposals.erpnext_proposals.utils.economic_calendar import (
	_ITEMS_FROZEN_FIELDS,
	_effective_behavior,
	_external_rate_source,
	_labor_rate_source,
)
from erpnext_proposals.erpnext_proposals.utils.print_format import resolve_sow_print_format

TEMPLATE = "_Test B9 Template"
ITEM = "_Test B9 Item"
CUSTOMER = "_Test B9 Customer"
SOW = "_Test B9 SOW PF"
SOW_ALT = "_Test B9 SOW PF Alt"


def _mk_pf(name):
	if not frappe.db.exists("Print Format", name):
		frappe.get_doc(
			{
				"doctype": "Print Format",
				"name": name,
				"doc_type": "Quotation",
				"module": "ERPNext Proposals",
				"print_format_type": "Jinja",
				"html": f"<div>{name}</div>",
				"standard": "No",
				"disabled": 0,
			}
		).insert(ignore_permissions=True)


class TestSowMaterialize(unittest.TestCase):
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
		_mk_pf(SOW)
		_mk_pf(SOW_ALT)
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "sow_print_format": SOW}
			).insert(ignore_permissions=True)
		cls.cost_center = get_test_cost_center(cls.company)
		cls._quotations = []

	@classmethod
	def tearDownClass(cls):
		frappe.db.set_value("Proposal Template", TEMPLATE, "sow_print_format", SOW, update_modified=False)
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

	def _make_draft(self, template=TEMPLATE):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": CUSTOMER,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": f"B9-{frappe.generate_hash(length=8)}",
				"proposal_template": template,
				"proposal_title": "B9",
				"proposal_cost_center": self.cost_center,
				"selling_price_list": get_test_price_list(),
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self._quotations.append(doc.name)
		return frappe.get_doc("Quotation", doc.name)

	def test_01_draft_materializes_sow_pf(self):
		doc = self._make_draft()
		self.assertEqual(doc.proposal_sow_print_format, SOW, "SOW PF materializado desde el template")
		self.assertEqual(resolve_sow_print_format(doc), SOW)

	def test_02_submitted_sow_unchanged_when_template_changes(self):
		doc = self._make_draft()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		# cambiar el SOW del Template tras formalizar NO debe afectar al submitted
		frappe.db.set_value("Proposal Template", TEMPLATE, "sow_print_format", SOW_ALT, update_modified=False)
		try:
			fresh = frappe.get_doc("Quotation", doc.name)
			self.assertEqual(
				fresh.proposal_sow_print_format, SOW, "el submitted conserva el SOW materializado"
			)
			self.assertEqual(
				resolve_sow_print_format(fresh), SOW, "submitted no relee el Template para el SOW"
			)
		finally:
			frappe.db.set_value("Proposal Template", TEMPLATE, "sow_print_format", SOW, update_modified=False)

	def test_03_no_sow_when_template_has_none(self):
		tpl = "_Test B9 Template NoSOW"
		if not frappe.db.exists("Proposal Template", tpl):
			frappe.get_doc({"doctype": "Proposal Template", "template_name": tpl}).insert(
				ignore_permissions=True
			)
		doc = self._make_draft(template=tpl)
		self.assertFalse(doc.proposal_sow_print_format, "sin SOW en el template → campo vacío")
		self.assertIsNone(resolve_sow_print_format(doc))


class TestEconomicFailClosed(unittest.TestCase):
	"""Los lectores económicos: fail-closed en formalizado, vivo en Draft."""

	def test_labor_frozen_missing_raises(self):
		row = frappe._dict({"designation": "X", "activity_type": "Y"})  # sin rate_source ni rate_locked
		with self.assertRaises(frappe.exceptions.ValidationError):
			_labor_rate_source(row, is_frozen=True)

	def test_labor_frozen_materialized_ok(self):
		row = frappe._dict({"costing_rate": 500, "rate_source": "matrix"})
		rate, source = _labor_rate_source(row, is_frozen=True)
		self.assertEqual(rate, 500.0)
		self.assertEqual(source, "matrix")

	def test_labor_draft_resolves_live(self):
		row = frappe._dict({"designation": "", "activity_type": ""})
		# Draft (is_frozen=False) NO lanza: resuelve en vivo (sin datos → 0/sin_datos).
		rate, source = _labor_rate_source(row, is_frozen=False)
		self.assertEqual(rate, 0.0)
		self.assertEqual(source, "sin_datos")

	def test_external_frozen_missing_raises(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			_external_rate_source(
				"ITEM", "Nos", None, is_frozen=True, locked=0, frozen_rate=0, frozen_source=""
			)

	def test_external_frozen_materialized_ok(self):
		rate, source = _external_rate_source(
			"ITEM", "Nos", None, is_frozen=True, locked=0, frozen_rate=300, frozen_source="buying_item_price"
		)
		self.assertEqual(rate, 300.0)
		self.assertEqual(source, "buying_item_price")

	def test_behavior_frozen_missing_raises(self):
		row = frappe._dict({})  # sin proposal_economic_behavior
		with self.assertRaises(frappe.exceptions.ValidationError):
			_effective_behavior(row, "ITEM", is_frozen=True, company="C", frozen_fields=_ITEMS_FROZEN_FIELDS)

	def test_behavior_frozen_materialized_ok(self):
		row = frappe._dict(
			{
				"proposal_economic_behavior": "recurring",
				"proposal_billing_interval": "Month",
				"proposal_billing_interval_count": 1,
			}
		)
		behavior, interval, count = _effective_behavior(
			row, "ITEM", is_frozen=True, company="C", frozen_fields=_ITEMS_FROZEN_FIELDS
		)
		self.assertEqual(behavior, "recurring")
		self.assertEqual(interval, "Month")
		self.assertEqual(count, 1)
