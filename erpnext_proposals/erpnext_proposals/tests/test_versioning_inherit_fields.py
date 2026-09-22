"""Versionado inherit-by-default: V2 conserva TODO el avance comercial de V1, excepto lo clasificado
como identidad/workflow/cadena/downstream/frozen/calculado.

Cubre todos los orígenes de Quotation (CRM Deal, Cliente directo, CRM sin Deal, Lead) + un test flagship
que compara sistemáticamente el estado comercial V1→V2 para protegernos de volver a perder campos.
"""

import unittest

import frappe
from frappe.utils import add_days, flt, today

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils import proposal_versioning as PV
from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import create_new_proposal_version


class TestVersioningInheritFields(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from erpnext_proposals.erpnext_proposals.tests.company import (
			get_test_company,
			get_test_item_group,
		)

		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company on test site.")
		cls._fy = ensure_current_fiscal_year()
		cls._extra = []

		# crm_deal Custom Field (el app `crm` no está instalado en el site de tests).
		if not frappe.db.exists("Custom Field", "Quotation-crm_deal"):
			frappe.get_doc(
				{
					"doctype": "Custom Field",
					"dt": "Quotation",
					"fieldname": "crm_deal",
					"label": "Frappe CRM Deal",
					"fieldtype": "Data",
					"read_only": 1,
					"insert_after": "party_name",
				}
			).insert(ignore_permissions=True)

		ig = get_test_item_group()
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or frappe.db.get_value(
			"Territory", {}, "name"
		)
		if not frappe.db.exists("Customer", "_IF Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_IF Customer",
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_IF Customer"

		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		if not frappe.db.exists("Item", "_IF Item"):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "_IF Item",
					"item_name": "_IF Item",
					"item_group": ig,
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
		cls.item = "_IF Item"

		cls.cost_center = frappe.db.get_value(
			"Cost Center", {"is_group": 0, "company": cls.company}, "name"
		) or frappe.db.get_value("Cost Center", {"is_group": 0}, "name")

		if not frappe.db.exists("Proposal Template", "_IF Template"):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": "_IF Template", "description": "IF"}
			).insert(ignore_permissions=True)
		cls.template = "_IF Template"

		# Contactos A (real de la propuesta) y B (primario simulado del Deal) para el test de contacto.
		cls.contact_a = cls._ensure_contact("_IF Contact A")
		cls.contact_b = cls._ensure_contact("_IF Contact B")

		# Cuenta para filas de impuesto (cualquier cuenta hoja de la company).
		cls.tax_account = frappe.db.get_value(
			"Account", {"company": cls.company, "account_type": "Tax", "is_group": 0}, "name"
		) or frappe.db.get_value("Account", {"company": cls.company, "is_group": 0}, "name")

		# Payment Terms Template (100% para el caso template).
		cls.ptt = cls._ensure_ptt()

	@classmethod
	def _ensure_contact(cls, name):
		if not frappe.db.exists("Contact", name):
			c = frappe.get_doc(
				{
					"doctype": "Contact",
					"first_name": name,
					"links": [{"link_doctype": "Customer", "link_name": cls.customer}],
				}
			)
			c.insert(ignore_permissions=True)
			return c.name
		return name

	@classmethod
	def _ensure_ptt(cls):
		if not frappe.db.exists("Payment Term", "_IF Full100"):
			frappe.get_doc(
				{
					"doctype": "Payment Term",
					"payment_term_name": "_IF Full100",
					"invoice_portion": 100,
					"due_date_based_on": "Day(s) after invoice date",
					"credit_days": 0,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Payment Terms Template", "_IF PTT"):
			frappe.get_doc(
				{
					"doctype": "Payment Terms Template",
					"template_name": "_IF PTT",
					"terms": [
						{
							"payment_term": "_IF Full100",
							"invoice_portion": 100,
							"due_date_based_on": "Day(s) after invoice date",
							"credit_days": 0,
						}
					],
				}
			).insert(ignore_permissions=True)
		return "_IF PTT"

	@classmethod
	def tearDownClass(cls):
		for name in getattr(cls, "_extra", []):
			if name and frappe.db.exists("Quotation", name):
				try:
					doc = frappe.get_doc("Quotation", name)
					if doc.docstatus == 1:
						doc.flags.ignore_linked_doctypes = True
						doc.cancel()
					frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
				except Exception:
					pass
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		super().tearDownClass()

	# ── builders ──────────────────────────────────────────────────────────────
	def _make_rejected(self, overrides=None, items=None, taxes=None, schedule=None):
		spec = {
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": self.customer,
			"company": self.company,
			"currency": "MXN",
			"transaction_date": today(),
			"proposal_group": f"IF-{frappe.generate_hash(length=6)}",
			"proposal_template": self.template,
			"proposal_title": "IF Rich",
			"items": items
			or [{"item_code": self.item, "item_name": "_IF Item", "qty": 1, "rate": 5000, "uom": "Nos"}],
		}
		if taxes:
			spec["taxes"] = taxes
		if schedule:
			spec["payment_schedule"] = schedule
		if overrides:
			spec.update(overrides)
		doc = frappe.get_doc(spec)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self._extra.append(doc.name)
		if self.cost_center:
			frappe.db.set_value(
				"Quotation", doc.name, "proposal_cost_center", self.cost_center, update_modified=False
			)
		doc.reload()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		frappe.db.set_value("Quotation", doc.name, "workflow_state", "Rechazada", update_modified=False)
		return frappe.get_doc("Quotation", doc.name)

	def _version(self, old, reason="rev"):
		v = create_new_proposal_version(old.name, reason=reason)
		self._extra.append(v)
		return frappe.get_doc("Quotation", v)

	def _reject(self, doc):
		frappe.db.set_value("Quotation", doc.name, "workflow_state", "Rechazada", update_modified=False)
		return frappe.get_doc("Quotation", doc.name)

	# ── 1. CRM Deal: V1→V2→V3 conserva crm_deal (+ contact_person) ──────────────
	def test_1_crm_deal_chain_preserved(self):
		v1 = self._make_rejected(overrides={"crm_deal": "CRM-DEAL-ABC", "contact_person": self.contact_a})
		self.assertEqual(v1.crm_deal, "CRM-DEAL-ABC")
		v2 = self._version(v1)
		self.assertEqual(v2.crm_deal, "CRM-DEAL-ABC", "V2 conserva crm_deal")
		self.assertEqual(v2.contact_person, self.contact_a, "V2 conserva contact_person")
		v2sub = self._reject_submit(v2)
		v3 = self._version(v2sub)
		self.assertEqual(v3.crm_deal, "CRM-DEAL-ABC", "V3 conserva crm_deal")
		self.assertEqual(v3.contact_person, self.contact_a, "V3 conserva contact_person")

	def _reject_submit(self, v):
		v.flags.ignore_mandatory = True
		v.flags.ignore_links = True
		v.submit()
		return self._reject(v)

	# ── 2. Cliente directo sin CRM ──────────────────────────────────────────────
	def test_2_customer_direct_no_crm(self):
		v1 = self._make_rejected(overrides={"contact_person": self.contact_a})
		v2 = self._version(v1)
		self.assertIn(v2.get("crm_deal") or "", ("", None), "sin crm_deal → vacío, sin error")
		self.assertEqual(v2.contact_person, self.contact_a)

	# ── 3. CRM instalado pero Quotation manual sin Deal ─────────────────────────
	def test_3_crm_installed_manual_no_deal(self):
		# El campo crm_deal existe pero vacío.
		v1 = self._make_rejected(overrides={"crm_deal": ""})
		v2 = self._version(v1)
		self.assertIn(v2.get("crm_deal") or "", ("", None))

	# ── 4. quotation_to=Lead (si el flujo lo soporta) ───────────────────────────
	def test_4_quotation_to_lead(self):
		lead = frappe.get_doc({"doctype": "Lead", "lead_name": "_IF Lead", "company_name": "_IF Lead Co"})
		lead.insert(ignore_permissions=True)
		self._extra_lead = lead.name
		v1 = self._make_rejected(overrides={"quotation_to": "Lead", "party_name": lead.name})
		v2 = self._version(v1)
		self.assertEqual(v2.quotation_to, "Lead")
		self.assertEqual(v2.party_name, lead.name)
		frappe.delete_doc("Lead", lead.name, force=True, ignore_permissions=True)

	# ── 5. FLAGSHIP: preservación integral del contenido comercial ──────────────
	def test_5_rich_commercial_preserved(self):
		vt = add_days(today(), 30)  # valid_till VIGENTE → se hereda LITERAL (ERPNext prohíbe vencido)
		taxes = None
		if self.tax_account:
			taxes = [
				{
					"charge_type": "On Net Total",
					"account_head": self.tax_account,
					"description": "IVA",
					"rate": 16,
				},
				{
					"charge_type": "Actual",
					"account_head": self.tax_account,
					"description": "Fijo",
					"tax_amount": 800,
				},
			]
		items = [
			{
				"item_code": self.item,
				"item_name": "_IF Item",
				"qty": 2,
				"rate": 5000,
				"uom": "Nos",
				"proposal_specific_scope": "Alcance específico capturado",
				"proposal_methodology": "<p>Metodología</p>",
			}
		]
		v1 = self._make_rejected(
			overrides={
				"crm_deal": "CRM-DEAL-RICH",
				"contact_person": self.contact_a,
				"valid_till": vt,
				"terms": "Condiciones comerciales acordadas.",
				"order_type": "Sales",
				"proposal_contract_term_months": 7,
				"proposal_financing_enabled": 1,
				"proposal_financed_amount": 1234.0,
				"proposal_financing_annual_cost_rate": 12.5,
				"payment_terms_template": self.ptt,
			},
			items=items,
			taxes=taxes,
		)
		v2 = self._version(v1)

		# Cabecera comercial idéntica
		self.assertEqual(v2.crm_deal, "CRM-DEAL-RICH")
		self.assertEqual(v2.contact_person, self.contact_a)
		self.assertEqual(str(v2.valid_till), str(vt), "valid_till vigente heredado LITERAL")
		self.assertEqual(v2.terms, "Condiciones comerciales acordadas.")
		self.assertEqual(v2.order_type, "Sales")
		self.assertEqual(v2.proposal_contract_term_months, 7)
		self.assertEqual(v2.proposal_financing_enabled, 1)
		self.assertEqual(flt(v2.proposal_financed_amount), 1234.0)
		self.assertEqual(flt(v2.proposal_financing_annual_cost_rate), 12.5)
		self.assertEqual(v2.payment_terms_template, self.ptt, "PTT heredado")
		self.assertEqual(v2.proposal_cost_center, v1.proposal_cost_center)
		self.assertEqual(v2.proposal_template, v1.proposal_template)
		self.assertEqual(v2.proposal_group, v1.proposal_group)

		# Items: contenido comercial
		self.assertEqual(len(v2.items), 1)
		self.assertEqual(v2.items[0].proposal_specific_scope, "Alcance específico capturado")
		# proposal_methodology se sincroniza desde el Item master → se compara por fidelidad V2↔V1.
		self.assertEqual(v2.items[0].proposal_methodology, v1.items[0].proposal_methodology)
		self.assertEqual(flt(v2.items[0].qty), 2)
		self.assertEqual(flt(v2.items[0].rate), 5000)

		# Impuestos: filas heredadas con FIDELIDAD al estado de V1 (ERPNext puede recalcular al submit;
		# el versionador copia lo que V1 realmente tiene). Comparamos V2 fila-a-fila contra V1.
		if taxes:
			self.assertEqual(len(v2.taxes), len(v1.taxes))
			for a, b in zip(v1.taxes, v2.taxes, strict=False):
				self.assertEqual(b.charge_type, a.charge_type)
				self.assertEqual(b.account_head, a.account_head)
				self.assertEqual(flt(b.rate), flt(a.rate))
				self.assertEqual(flt(b.tax_amount), flt(a.tax_amount), "tax_amount heredado idéntico a V1")

		# Cadena / identidad
		self.assertEqual(v2.proposal_version, v1.proposal_version + 1)
		self.assertEqual(v2.previous_proposal, v1.name)
		self.assertIn(v2.get("superseded_by_proposal") or "", ("", None))
		self.assertIn(v2.get("proposal_project") or "", ("", None))
		self.assertEqual(v2.workflow_state, "Borrador")
		self.assertEqual(str(v2.transaction_date), today())

	# ── 6. Payment Schedule manual preservado (sin throw) ───────────────────────
	def test_6_manual_payment_schedule_preserved(self):
		sched = [
			{
				"description": "50% anticipo",
				"invoice_portion": 50,
				"payment_amount": 2500,
				"due_date": today(),
			},
			{
				"description": "50% contra entrega",
				"invoice_portion": 50,
				"payment_amount": 2500,
				"due_date": add_days(today(), 30),
			},
		]
		v1 = self._make_rejected(schedule=sched)
		self.assertEqual(len(v1.payment_schedule), 2)
		v2 = self._version(v1)  # NO debe lanzar throw
		self.assertEqual(len(v2.payment_schedule), 2, "filas manuales preservadas")
		descs = {r.description for r in v2.payment_schedule}
		self.assertEqual(descs, {"50% anticipo", "50% contra entrega"})
		self.assertIn(v2.get("payment_terms_template") or "", ("", None))

	# ── 7. Payment Terms Template: heredado; schedule regenerado ────────────────
	def test_7_payment_terms_template_regenerates(self):
		v1 = self._make_rejected(overrides={"payment_terms_template": self.ptt})
		v2 = self._version(v1)
		self.assertEqual(v2.payment_terms_template, self.ptt, "template heredado")

	# ── 8. Taxes con charge_type=Actual ─────────────────────────────────────────
	def test_8_taxes_actual_inherited(self):
		if not self.tax_account:
			self.skipTest("no tax account")
		taxes = [
			{
				"charge_type": "Actual",
				"account_head": self.tax_account,
				"description": "Fijo",
				"tax_amount": 999,
			}
		]
		v1 = self._make_rejected(taxes=taxes)
		v2 = self._version(v1)
		self.assertEqual(len(v2.taxes), len(v1.taxes))
		self.assertEqual(
			flt(v2.taxes[0].tax_amount),
			flt(v1.taxes[0].tax_amount),
			"la fila de impuesto (tax_amount) se hereda idéntica a V1",
		)
		self.assertEqual(v2.taxes[0].charge_type, v1.taxes[0].charge_type)

	# ── 9. Economía materializada se hereda; flags legacy de lock no (B7 / ADR-0022) ────────────
	def test_9_economics_inherited_locks_not(self):
		v1 = self._make_rejected()
		# Flujo nuevo: la línea vendida tiene economía MATERIALIZADA (marcadores *_source / behavior).
		self.assertTrue(
			v1.items[0].get("proposal_frozen_cost_source"), "precondición: costo externo materializado"
		)
		self.assertTrue(
			v1.items[0].get("proposal_economic_behavior"), "precondición: comportamiento materializado"
		)
		v2 = self._version(v1)
		it = v2.items[0]
		# Los VALORES económicos se heredan (Draft autosuficiente; resync refresca).
		self.assertEqual(
			it.get("proposal_frozen_cost_source"), v1.items[0].get("proposal_frozen_cost_source")
		)
		self.assertEqual(
			flt(it.get("proposal_frozen_cost_rate")), flt(v1.items[0].get("proposal_frozen_cost_rate"))
		)
		self.assertEqual(it.get("proposal_economic_behavior"), v1.items[0].get("proposal_economic_behavior"))
		# El flag legacy de lock NO se hereda (ni se usa en el flujo nuevo).
		self.assertFalse(it.get("proposal_cost_locked"), "el flag legacy proposal_cost_locked no se hereda")

	# ── 10. Cadena V1→V2→V3 intacta ─────────────────────────────────────────────
	def test_10_chain_intact(self):
		v1 = self._make_rejected()
		v2 = self._version(v1)
		self.assertEqual(frappe.db.get_value("Quotation", v1.name, "superseded_by_proposal"), v2.name)
		v2sub = self._reject_submit(v2)
		v3 = self._version(v2sub)
		self.assertEqual(v3.proposal_version, 3)
		self.assertEqual(v3.previous_proposal, v2.name)
		self.assertEqual(frappe.db.get_value("Quotation", v2.name, "superseded_by_proposal"), v3.name)

	# ── 11. Cobertura meta-driven: nombres EXCLUDE/FORCE válidos + sin pérdidas ──
	def test_11_meta_coverage(self):
		# 11a: cada nombre en EXCLUDE/FORCE_INCLUDE existe en el meta de su DocType (sin typos/stale).
		for dt, names in PV._EXCLUDE.items():
			meta = frappe.get_meta(dt)
			valid = {df.fieldname for df in meta.fields}
			for fn in names:
				self.assertIn(fn, valid, f"EXCLUDE['{dt}'] tiene campo inexistente: {fn}")
		for dt, names in PV._FORCE_INCLUDE.items():
			meta = frappe.get_meta(dt)
			valid = {df.fieldname for df in meta.fields}
			for fn in names:
				self.assertIn(fn, valid, f"FORCE_INCLUDE['{dt}'] tiene campo inexistente: {fn}")

		# 11b: todo campo comercial poblado (no_copy=0, no en EXCLUDE, no computado) se hereda.
		computed_skip = {
			"customer_name",
			"contact_display",
			"contact_email",
			"contact_mobile",
			"contact_phone",
			"address_display",
			"company_address_display",
			"net_total",
			"base_net_total",
			"total",
			"base_total",
			"grand_total",
			"base_grand_total",
			"rounded_total",
			"base_rounded_total",
			"total_taxes_and_charges",
			"base_total_taxes_and_charges",
			"total_qty",
			"total_net_weight",
			"rounding_adjustment",
			"base_rounding_adjustment",
			"conversion_rate",
			"plc_conversion_rate",
			"in_words",
			"base_in_words",
			"disable_rounded_total",
			"total_lead_time_days",
			"party_name",  # se hereda pero puede recomputar customer_name
		}
		v1 = self._make_rejected(
			overrides={
				"crm_deal": "CRM-COV",
				"contact_person": self.contact_a,
				"valid_till": add_days(today(), 10),
				"terms": "T&C",
				"proposal_contract_term_months": 4,
			}
		)
		v2 = self._version(v1)
		meta = frappe.get_meta("Quotation")
		exclude = PV._EXCLUDE["Quotation"]
		lost = []
		for df in meta.fields:
			fn = df.fieldname
			if df.fieldtype in PV._LAYOUT_FT or df.fieldtype in ("Table", "Table MultiSelect"):
				continue
			if df.no_copy or fn in exclude or fn in PV._SYS_EXCLUDE or fn in computed_skip:
				continue
			old_v = v1.get(fn)
			if old_v in (None, "", 0, 0.0):
				continue
			if v2.get(fn) != old_v:
				lost.append((fn, old_v, v2.get(fn)))
		self.assertEqual(lost, [], f"campos comerciales perdidos por el versionador: {lost}")

	# ── 12. contact_person heredado NO lo sobrescribe el Deal durante versionado ─
	def test_12_contact_not_overwritten_during_versioning(self):
		# V1 se crea SIN mock → conserva el contacto A capturado en la propuesta.
		v1 = self._make_rejected(overrides={"crm_deal": "CRM-DEAL-X", "contact_person": self.contact_a})
		self.assertEqual(v1.contact_person, self.contact_a, "precondición: V1 con contacto A")
		# Ahora simulamos que el Deal tiene un contacto primario DISTINTO (B) y versionamos.
		orig = PV_contact_module()._deal_primary_contact
		PV_contact_module()._deal_primary_contact = lambda deal: self.contact_b
		try:
			v2 = self._version(v1)
			self.assertEqual(
				v2.contact_person,
				self.contact_a,
				"el versionado conserva el contacto heredado; no lo sustituye por el primario del Deal",
			)
		finally:
			PV_contact_module()._deal_primary_contact = orig

	# ── 13. valid_till vencido → en blanco (ERPNext prohíbe valid_till < transaction_date) ──────
	def test_13_valid_till_expired_blanked(self):
		v1 = self._make_rejected(overrides={"valid_till": add_days(today(), 30)})
		# Simular el paso del tiempo: la vigencia quedó en el pasado (db_set evita validate_valid_till).
		frappe.db.set_value("Quotation", v1.name, "valid_till", add_days(today(), -10), update_modified=False)
		v1.reload()
		v2 = self._version(v1)  # no debe lanzar; ERPNext rechazaría un valid_till vencido en la Draft
		self.assertIn(v2.get("valid_till") or "", ("", None), "valid_till vencido → en blanco en V2")


def PV_contact_module():
	from erpnext_proposals.erpnext_proposals.utils import quotation_contact

	return quotation_contact
