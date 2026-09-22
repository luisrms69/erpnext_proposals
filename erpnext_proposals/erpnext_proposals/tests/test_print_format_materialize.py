# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Print Format materializado en la Quotation (B8 / ADR-0022).

El Print Format comercial efectivo se resuelve durante Draft y se PERSISTE en `proposal_print_format`
(campo normal); `docstatus=1` lo vuelve inmutable. El flujo nuevo NO escribe
`proposal_effective_print_format`. ADR-0011: un PF usado por una propuesta formalizada (docstatus=1) es
histórico. El resolver respeta el legacy `proposal_effective_print_format` para documentos antiguos.
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
from erpnext_proposals.erpnext_proposals.utils.print_format import resolve_commercial_print_format
from erpnext_proposals.erpnext_proposals.utils.print_format_protection import is_print_format_historical

TEMPLATE = "_Test B8 Template"
ITEM = "_Test B8 Item"
CUSTOMER = "_Test B8 Customer"
PF = "_Test B8 PF"

_IMMUTABLE_EXCEPTIONS = (
	frappe.exceptions.ValidationError,
	frappe.exceptions.UpdateAfterSubmitError,
)


class TestPrintFormatMaterialize(unittest.TestCase):
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
		if not frappe.db.exists("Print Format", PF):
			frappe.get_doc(
				{
					"doctype": "Print Format",
					"name": PF,
					"doc_type": "Quotation",
					"module": "ERPNext Proposals",
					"print_format_type": "Jinja",
					"html": "<div>B8</div>",
					"standard": "No",
					"disabled": 0,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "print_format": PF}
			).insert(ignore_permissions=True)
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
				"proposal_group": f"B8-{frappe.generate_hash(length=8)}",
				"proposal_template": TEMPLATE,
				"proposal_title": "B8",
				"proposal_cost_center": self.cost_center,
				"selling_price_list": get_test_price_list(),
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self._quotations.append(doc.name)
		return frappe.get_doc("Quotation", doc.name)

	def _submit(self):
		doc = self._make_draft()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		return frappe.get_doc("Quotation", doc.name)

	# ── Draft materializa el PF (campo normal), sin escribir el efectivo legacy ─

	def test_01_draft_materializes_print_format(self):
		doc = self._make_draft()
		self.assertEqual(doc.docstatus, 0)
		self.assertEqual(doc.proposal_print_format, PF, "PF materializado desde el template en Draft")
		self.assertFalse(
			(doc.get("proposal_effective_print_format") or ""),
			"el flujo nuevo no escribe proposal_effective_print_format",
		)

	def test_02_default_persisted_when_template_has_no_pf(self):
		# Un template sin print_format → se materializa y persiste el DEFAULT (antes quedaba vacío).
		tpl = "_Test B8 Template NoPF"
		if not frappe.db.exists("Proposal Template", tpl):
			frappe.get_doc({"doctype": "Proposal Template", "template_name": tpl}).insert(
				ignore_permissions=True
			)
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": CUSTOMER,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": f"B8N-{frappe.generate_hash(length=8)}",
				"proposal_template": tpl,
				"proposal_title": "B8 NoPF",
				"proposal_cost_center": self.cost_center,
				"selling_price_list": get_test_price_list(),
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self._quotations.append(doc.name)
		self.assertEqual(
			frappe.get_doc("Quotation", doc.name).proposal_print_format,
			"Propuesta Comercial",
			"DEFAULT materializado y persistido cuando el template no define PF",
		)

	# ── formalizado: resolver usa el materializado + es histórico (ADR-0011) ────

	def test_03_submitted_uses_materialized_and_is_historical(self):
		doc = self._submit()
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(resolve_commercial_print_format(doc), PF, "resuelve el PF materializado")
		self.assertFalse((doc.get("proposal_effective_print_format") or ""))
		self.assertTrue(
			is_print_format_historical(PF), "ADR-0011: PF usado por propuesta formalizada = histórico"
		)

	def test_04_draft_pf_not_historical(self):
		# Solo Draft (no formalizado) → el PF aún NO es histórico por esta propuesta.
		tpl = "_Test B8 Template Solo"
		pf2 = "_Test B8 PF Solo"
		if not frappe.db.exists("Print Format", pf2):
			frappe.get_doc(
				{
					"doctype": "Print Format",
					"name": pf2,
					"doc_type": "Quotation",
					"module": "ERPNext Proposals",
					"print_format_type": "Jinja",
					"html": "<div>B8 solo</div>",
					"standard": "No",
					"disabled": 0,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", tpl):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": tpl, "print_format": pf2}
			).insert(ignore_permissions=True)
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": CUSTOMER,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": f"B8S-{frappe.generate_hash(length=8)}",
				"proposal_template": tpl,
				"proposal_title": "B8 Solo",
				"proposal_cost_center": self.cost_center,
				"selling_price_list": get_test_price_list(),
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self._quotations.append(doc.name)
		self.assertFalse(is_print_format_historical(pf2), "un Draft no vuelve histórico al PF")

	# ── inmutable por docstatus ─────────────────────────────────────────────────

	def test_05_submitted_pf_immutable(self):
		doc = self._submit()
		fresh = frappe.get_doc("Quotation", doc.name)
		fresh.proposal_print_format = "Propuesta Comercial"
		with self.assertRaises(_IMMUTABLE_EXCEPTIONS):
			fresh.save()

	# ── fallback legacy: documento histórico con effective ──────────────────────

	def test_06_legacy_effective_still_resolved(self):
		legacy = frappe._dict(
			{"proposal_effective_print_format": PF, "proposal_print_format": "Propuesta Comercial"}
		)
		self.assertEqual(
			resolve_commercial_print_format(legacy), PF, "el histórico usa proposal_effective_print_format"
		)
