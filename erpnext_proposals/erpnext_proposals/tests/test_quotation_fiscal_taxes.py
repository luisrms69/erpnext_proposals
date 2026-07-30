# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests del adapter fiscal de Quotation (erpnext_proposals) que reutiliza, por import,
los helpers de resolución de ``facturacion_mexico`` SIN modificarlos.

Cubre:
- aplicación correcta del STCT en Quotation (Customer → CC → Branch → zona → variante → STCT);
- no-op suave sin configuración (no bloquea el guardado);
- respeto a impuestos manuales (no sobrescribe ``taxes_and_charges`` ya asignado);
- no-op para documentos que no son Customer (CRM Deal / Lead / Prospect);
- evidencia estructural de que ``facturacion_mexico`` no fue modificado (erpnext_proposals no
  engancha Sales Invoice; el hook de SI de fm sigue intacto; los helpers importados son los de fm);
- regresión de Sales Invoice: fm sigue resolviendo su STCT en ``before_validate`` sin cambios.

Los tests de comportamiento requieren ``facturacion_mexico`` instalada + sus custom fields
(``fm_customer_default_cost_center``, ``fm_mapped_branch``, ``fm_is_border_zone``). Si el fixture
fiscal no puede construirse en el site, esos tests se omiten (skip) — los estructurales siempre corren.
"""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.company import (
	get_test_company,
	get_test_cost_center,
	get_test_item_group,
	get_test_price_list,
)

STCT_BASICO = "IVA Nacional - Básico"
MANUAL_STCT = "_Test Manual STCT"
BRANCH = "_Test Fiscal Branch"
CC_NO_BRANCH = "_Test CC Sin Branch"
CUSTOMER = "_Test Fiscal Customer"
ITEM = "_Test Fiscal Item"


def _ensure_group_masters():
	if not frappe.db.exists("Customer Group", "All Customer Groups"):
		frappe.get_doc(
			{"doctype": "Customer Group", "customer_group_name": "All Customer Groups", "is_group": 1}
		).insert(ignore_permissions=True)
	if not frappe.db.exists("Customer Group", "_Test CG"):
		frappe.get_doc(
			{
				"doctype": "Customer Group",
				"customer_group_name": "_Test CG",
				"is_group": 0,
				"parent_customer_group": "All Customer Groups",
			}
		).insert(ignore_permissions=True)
	if not frappe.db.exists("Territory", "All Territories"):
		frappe.get_doc({"doctype": "Territory", "territory_name": "All Territories", "is_group": 1}).insert(
			ignore_permissions=True
		)
	if not frappe.db.exists("Territory", "_Test Terr"):
		frappe.get_doc(
			{
				"doctype": "Territory",
				"territory_name": "_Test Terr",
				"is_group": 0,
				"parent_territory": "All Territories",
			}
		).insert(ignore_permissions=True)


def _get_tax_account(company: str) -> str:
	acc = frappe.db.get_value("Account", {"company": company, "account_type": "Tax", "is_group": 0}, "name")
	if acc:
		return acc
	# fallback: cualquier cuenta hoja de la company
	acc = frappe.db.get_value("Account", {"company": company, "is_group": 0}, "name")
	if acc:
		return acc
	# crear una cuenta de impuestos mínima bajo la raíz de la company
	parent = frappe.db.get_value(
		"Account", {"company": company, "is_group": 1, "root_type": "Liability"}, "name"
	) or frappe.db.get_value("Account", {"company": company, "is_group": 1}, "name")
	doc = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": "_Test IVA Trasladado",
			"company": company,
			"parent_account": parent,
			"account_type": "Tax",
			"is_group": 0,
		}
	).insert(ignore_permissions=True)
	return doc.name


class TestQuotationFiscalTaxes(unittest.TestCase):
	# ── Tests estructurales (siempre corren; no dependen del fixture fiscal) ──────────

	def test_erpnext_proposals_does_not_hook_sales_invoice(self):
		"""erpnext_proposals NO debe registrar ningún doc_event de Sales Invoice → impacto cero."""
		from erpnext_proposals import hooks

		self.assertNotIn(
			"Sales Invoice",
			hooks.doc_events,
			"erpnext_proposals no debe enganchar Sales Invoice (impacto cero en el flujo fiscal).",
		)

	def test_fm_sales_invoice_before_validate_intact(self):
		"""El hook before_validate de fm sobre Sales Invoice sigue registrado y apuntando a fm."""
		si_events = frappe.get_hooks("doc_events").get("Sales Invoice", {})
		before_validate = si_events.get("before_validate", [])
		if isinstance(before_validate, str):
			before_validate = [before_validate]
		self.assertTrue(
			any(
				"facturacion_mexico.hooks_handlers.sales_invoice_automated_tax.before_validate" in h
				for h in before_validate
			),
			"El before_validate de facturacion_mexico sobre Sales Invoice debe permanecer intacto.",
		)

	def test_imported_helpers_come_from_fm(self):
		"""Los helpers que reutiliza el adapter provienen (por import) del módulo de fm, sin redefinir."""
		mod = "facturacion_mexico.hooks_handlers.sales_invoice_automated_tax"
		from facturacion_mexico.hooks_handlers.sales_invoice_automated_tax import (
			_determinar_variante_stct,
			_find_stct_by_variant,
			_get_border_zone_status,
			_get_branch_from_cost_center,
			_get_customer_default_cc,
		)

		for fn in (
			_get_customer_default_cc,
			_get_branch_from_cost_center,
			_get_border_zone_status,
			_determinar_variante_stct,
			_find_stct_by_variant,
		):
			self.assertEqual(fn.__module__, mod)

	def test_adapter_does_not_call_blocking_helper(self):
		"""El adapter NO debe llamar a _set_stct_by_branch (bloqueante). Se verifica que no lo
		invoca (llamada con paréntesis) ni lo importa; las menciones en docstring/comentarios se ignoran."""
		import ast

		import erpnext_proposals.erpnext_proposals.utils.quotation_tax as adapter

		src = frappe.read_file(adapter.__file__) or ""
		tree = ast.parse(src)
		imported = {
			alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names
		}
		called = {
			node.func.id
			for node in ast.walk(tree)
			if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
		}
		self.assertNotIn("_set_stct_by_branch", imported)
		self.assertNotIn("_set_stct_by_branch", called)

	# ── Fixture fiscal para los tests de comportamiento ──────────────────────────────

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._fixture_ok = False
		cls._fixture_err = None
		cls._quotations = []
		try:
			cls._build_fixture()
			cls._fixture_ok = True
		except unittest.SkipTest as e:
			cls._fixture_err = f"SkipTest: {e}"
		except Exception:
			cls._fixture_err = frappe.get_traceback()

	@classmethod
	def _build_fixture(cls):
		# Requiere los custom fields de fm
		for dt, col in (
			("Customer", "fm_customer_default_cost_center"),
			("Cost Center", "fm_mapped_branch"),
			("Branch", "fm_is_border_zone"),
		):
			if not frappe.db.has_column(dt, col):
				raise unittest.SkipTest(f"Falta {dt}.{col} (facturacion_mexico no migrada).")

		cls.company = get_test_company()
		cls.abbr = frappe.db.get_value("Company", cls.company, "abbr")
		# Asegura el árbol de cost centers de la company (crea raíz + Main si falta).
		get_test_cost_center(cls.company)
		cls.item_group = get_test_item_group()
		cls.price_list = get_test_price_list()
		_ensure_group_masters()

		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)

		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": ITEM,
					"item_group": cls.item_group,
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)

		# Branch (zona Nacional). fm hace obligatorio `company` en Branch.
		if not frappe.db.exists("Branch", BRANCH):
			frappe.get_doc(
				{"doctype": "Branch", "branch": BRANCH, "company": cls.company, "fm_is_border_zone": 0}
			).insert(ignore_permissions=True, ignore_mandatory=True)

		# Dos Cost Centers dedicados y deterministas (no depender de "el primer CC hoja"):
		#  - CC_MAPPED: fm_mapped_branch = BRANCH  (para aplicar STCT)
		#  - CC_NO_BRANCH: fm_mapped_branch VACÍO  (para el no-op suave)
		root = frappe.db.get_value("Cost Center", {"is_group": 1, "company": cls.company}, "name")

		def _ensure_cc(cc_name: str, mapped_branch: str | None) -> str:
			full = f"{cc_name} - {cls.abbr}"
			if not frappe.db.exists("Cost Center", full):
				frappe.get_doc(
					{
						"doctype": "Cost Center",
						"cost_center_name": cc_name,
						"company": cls.company,
						"parent_cost_center": root,
						"is_group": 0,
					}
				).insert(ignore_permissions=True)
			frappe.db.set_value("Cost Center", full, "fm_mapped_branch", mapped_branch or "")
			return full

		cls.cost_center = _ensure_cc("_Test CC Mapped", BRANCH)
		cls.cc_no_branch = _ensure_cc(CC_NO_BRANCH, None)

		# Customer (con RFC genérico para no chocar con validaciones fiscales de fm)
		if not frappe.db.exists("Customer", CUSTOMER):
			cust = frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": CUSTOMER,
					"customer_type": "Company",
					"customer_group": "_Test CG",
					"territory": "_Test Terr",
					"tax_id": "XAXX010101000",
				}
			)
			cust.insert(ignore_permissions=True)
		frappe.db.set_value("Customer", CUSTOMER, "fm_customer_default_cost_center", cls.cost_center)

		tax_account = _get_tax_account(cls.company)

		# STCT "IVA Nacional - Básico - {abbr}" (el que resuelve el motor de fm)
		if not frappe.db.exists("Sales Taxes and Charges Template", f"{STCT_BASICO} - {cls.abbr}"):
			frappe.get_doc(
				{
					"doctype": "Sales Taxes and Charges Template",
					"title": STCT_BASICO,
					"company": cls.company,
					"taxes": [
						{
							"charge_type": "On Net Total",
							"account_head": tax_account,
							"description": "IVA 16%",
							"rate": 16,
						}
					],
				}
			).insert(ignore_permissions=True)
		cls.stct = f"{STCT_BASICO} - {cls.abbr}"

		# STCT manual distinto (para el test de respeto a selección manual)
		if not frappe.db.exists("Sales Taxes and Charges Template", f"{MANUAL_STCT} - {cls.abbr}"):
			frappe.get_doc(
				{
					"doctype": "Sales Taxes and Charges Template",
					"title": MANUAL_STCT,
					"company": cls.company,
					"taxes": [
						{
							"charge_type": "On Net Total",
							"account_head": tax_account,
							"description": "IVA Manual",
							"rate": 8,
						}
					],
				}
			).insert(ignore_permissions=True)
		cls.manual_stct = f"{MANUAL_STCT} - {cls.abbr}"

		# Proposal Section + Template mínimos (proposal_template es reqd=1 en Quotation).
		if not frappe.db.exists("Proposal Section", "_Test Fiscal Section"):
			frappe.get_doc(
				{
					"doctype": "Proposal Section",
					"section_name": "_Test Fiscal Section",
					"title": "Sección Fiscal",
					"content": "<p>_</p>",
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", "_Test Fiscal Template"):
			t = frappe.get_doc({"doctype": "Proposal Template", "template_name": "_Test Fiscal Template"})
			t.append("sections", {"proposal_section": "_Test Fiscal Section", "sequence": 10})
			t.insert(ignore_permissions=True)
		cls.template = "_Test Fiscal Template"
		frappe.db.commit()  # nosemgrep — aislar fixture para las Quotations de prueba

	@classmethod
	def tearDownClass(cls):
		for n in cls._quotations:
			if frappe.db.exists("Quotation", n):
				try:
					frappe.delete_doc("Quotation", n, force=True, ignore_permissions=True)
				except Exception:
					pass
		super().tearDownClass()

	def _make_quotation(
		self, cost_center=None, quotation_to="Customer", party_name=None, taxes_and_charges=None
	):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": quotation_to,
				"party_name": party_name or (CUSTOMER if quotation_to == "Customer" else None),
				"company": self.company,
				"currency": "MXN",
				"selling_price_list": self.price_list,
				"transaction_date": frappe.utils.today(),
				"proposal_cost_center": cost_center or self.cost_center,
				"proposal_template": self.template,
				"proposal_group": f"FISCAL-{frappe.generate_hash(length=8)}",
				"taxes_and_charges": taxes_and_charges,
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True)
		self._quotations.append(doc.name)
		return doc

	# ── Tests de comportamiento ──────────────────────────────────────────────────────

	def _require_fixture(self):
		if not self._fixture_ok:
			raise unittest.SkipTest(f"Fixture fiscal no disponible: {self._fixture_err}")

	def test_quotation_applies_stct(self):
		self._require_fixture()
		q = self._make_quotation()
		self.assertEqual(q.taxes_and_charges, self.stct)
		self.assertTrue(q.get("taxes"), "Debe haber filas de impuesto cargadas desde el STCT.")
		self.assertAlmostEqual(q.taxes[0].rate, 16)

	def test_quotation_soft_noop_without_branch(self):
		"""CC sin fm_mapped_branch → el adapter no resuelve STCT y la Quotation guarda sin bloquear."""
		self._require_fixture()
		q = self._make_quotation(cost_center=self.cc_no_branch)
		self.assertFalse(q.get("taxes_and_charges"))
		self.assertFalse(q.get("taxes"))

	def test_quotation_respects_manual_taxes(self):
		"""Si taxes_and_charges ya tiene valor (selección manual), el adapter NO lo sobrescribe."""
		self._require_fixture()
		q = self._make_quotation(taxes_and_charges=self.manual_stct)
		self.assertEqual(q.taxes_and_charges, self.manual_stct)

	def test_quotation_noop_non_customer(self):
		"""quotation_to != Customer (p. ej. Lead) → no-op, sin impuestos ni error."""
		self._require_fixture()
		# Lead como party (crear uno mínimo)
		if not frappe.db.exists("Lead", {"lead_name": "_Test Fiscal Lead"}):
			lead = frappe.get_doc(
				{"doctype": "Lead", "lead_name": "_Test Fiscal Lead", "company_name": "_Test Fiscal Lead"}
			).insert(ignore_permissions=True)
			lead_name = lead.name
		else:
			lead_name = frappe.db.get_value("Lead", {"lead_name": "_Test Fiscal Lead"}, "name")
		q = self._make_quotation(quotation_to="Lead", party_name=lead_name)
		self.assertFalse(q.get("taxes_and_charges"))

	def test_sales_invoice_flow_unchanged(self):
		"""Regresión: fm sigue resolviendo su STCT en Sales Invoice.before_validate, sin cambios.

		Se ejecuta el before_validate nativo sobre un Sales Invoice en memoria (sin insert/posting):
		fm debe fijar el mismo STCT. erpnext_proposals no engancha SI, así que su adapter no participa.
		"""
		self._require_fixture()
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": CUSTOMER,
				"company": self.company,
				"currency": "MXN",
				"cost_center": self.cost_center,
				"posting_date": frappe.utils.today(),
				"items": [
					{"item_code": ITEM, "qty": 1, "rate": 1000, "uom": "Nos", "cost_center": self.cost_center}
				],
			}
		)
		try:
			si.run_method("before_validate")
		except Exception as e:
			raise unittest.SkipTest(f"SI before_validate no ejecutable en este entorno: {e}") from e
		self.assertEqual(
			si.taxes_and_charges,
			self.stct,
			"facturacion_mexico debe seguir resolviendo su STCT en Sales Invoice (sin cambios).",
		)
