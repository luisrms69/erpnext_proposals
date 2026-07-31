# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests de la resolución/persistencia del contacto dirigido de la Quotation
(`utils/quotation_contact.py`).

Cubre: nueva Quotation (before_insert, fallback del Customer), **ruta principal Deal → contacto del
Deal prevalece** sobre el default del Customer, autocorrección de Draft antiguo sin contacto al guardar
(validate), no sobrescritura de un contacto ya definido, no-op para Submitted y para
``quotation_to != Customer``, guard de la rama del Deal (sin app ``crm``) y **prioridad interna de
``_deal_primary_contact``** (fila ``is_primary`` → ``CRM Deal.contact`` → primera fila).

El site de tests no tiene el app ``crm`` (ni el DocType ``CRM Deal``). La rama "contacto del Deal" se
ejercita con **mocking/stubbing**: ``_deal_primary_contact`` se parcha para las pruebas de precedencia
(before_insert), y para su prioridad interna se parchan las consultas ``frappe.db``/``get_all``.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.contacts.doctype.contact.contact import get_default_contact

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
from erpnext_proposals.erpnext_proposals.utils import quotation_contact as qc
from erpnext_proposals.erpnext_proposals.utils.quotation_contact import (
	_deal_primary_contact,
	autocorrect_missing_contact,
)

CUSTOMER = "_Test Contact Customer"
CONTACT_EMAIL = "dirigido@example.com"
CONTACT_MOBILE = "5555550123"
DEAL_CONTACT_EMAIL = "deal-a@example.com"
DEAL_CONTACT_MOBILE = "5555559999"
ITEM = "_Test Contact Item"
TEMPLATE = "_Test Contact Template"
SECTION = "_Test Contact Section"


def _ensure_group_masters():
	for dt, gname in (("Customer Group", "All Customer Groups"), ("Territory", "All Territories")):
		if not frappe.db.exists(dt, gname):
			frappe.get_doc(
				{"doctype": dt, dt.lower().replace(" ", "_") + "_name": gname, "is_group": 1}
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
	if not frappe.db.exists("Territory", "_Test Terr"):
		frappe.get_doc(
			{
				"doctype": "Territory",
				"territory_name": "_Test Terr",
				"is_group": 0,
				"parent_territory": "All Territories",
			}
		).insert(ignore_permissions=True)


class TestQuotationContact(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._quotations = []
		cls._fy = ensure_current_fiscal_year()
		cls.company = get_test_company()
		cls.cost_center = get_test_cost_center(cls.company)
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

		if not frappe.db.exists("Customer", CUSTOMER):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": CUSTOMER,
					"customer_type": "Company",
					"customer_group": "_Test CG",
					"territory": "_Test Terr",
					"tax_id": "XAXX010101000",
				}
			).insert(ignore_permissions=True)

		# Contacto (con email + móvil) ligado al Customer por Dynamic Link. Idempotente por first_name
		# (el autoname del Contact incorpora el party).
		if not frappe.get_all("Contact", filters={"first_name": "_Test Dirigido"}, limit=1):
			c = frappe.get_doc(
				{
					"doctype": "Contact",
					"first_name": "_Test Dirigido",
					"last_name": "Contact",
					"is_primary_contact": 1,
				}
			)
			c.append("email_ids", {"email_id": CONTACT_EMAIL, "is_primary": 1})
			c.append("phone_nos", {"phone": CONTACT_MOBILE, "is_primary_mobile_no": 1})
			c.append("links", {"link_doctype": "Customer", "link_name": CUSTOMER})
			c.insert(ignore_permissions=True)
		# Segundo contacto del mismo Customer (para el test de "no sobrescribir").
		if not frappe.get_all("Contact", filters={"first_name": "_Test Otro"}, limit=1):
			o = frappe.get_doc({"doctype": "Contact", "first_name": "_Test Otro"})
			o.append("links", {"link_doctype": "Customer", "link_name": CUSTOMER})
			o.insert(ignore_permissions=True)
		cls.otro = frappe.get_all("Contact", filters={"first_name": "_Test Otro"}, pluck="name")[0]
		# Contacto "del Deal" (A): contacto legítimo del Customer (ligado por Dynamic Link) pero NO el
		# is_primary_contact — el default nativo del Customer sigue siendo B. Refleja el flujo real: el
		# contacto del Deal pertenece al Customer, y ERPNext valida esa pertenencia al fijar contact_person.
		if not frappe.get_all("Contact", filters={"first_name": "_Test Deal A"}, limit=1):
			a = frappe.get_doc({"doctype": "Contact", "first_name": "_Test Deal A", "last_name": "Deal"})
			a.append("email_ids", {"email_id": DEAL_CONTACT_EMAIL, "is_primary": 1})
			a.append("phone_nos", {"phone": DEAL_CONTACT_MOBILE, "is_primary_mobile_no": 1})
			a.append("links", {"link_doctype": "Customer", "link_name": CUSTOMER})
			a.insert(ignore_permissions=True)
		cls.deal_contact = frappe.get_all("Contact", filters={"first_name": "_Test Deal A"}, pluck="name")[0]
		# Asegurar el Dynamic Link al Customer (idempotente en el site de tests persistente).
		a_doc = frappe.get_doc("Contact", cls.deal_contact)
		if not any(link.link_doctype == "Customer" and link.link_name == CUSTOMER for link in a_doc.links):
			a_doc.append("links", {"link_doctype": "Customer", "link_name": CUSTOMER})
			a_doc.save(ignore_permissions=True)
		# Fuente de verdad de lo que el código resolverá para este Customer (fallback nativo).
		cls.contact = get_default_contact("Customer", CUSTOMER)

		if not frappe.db.exists("Proposal Section", SECTION):
			frappe.get_doc(
				{
					"doctype": "Proposal Section",
					"section_name": SECTION,
					"title": "Sec",
					"content": "<p>_</p>",
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			t = frappe.get_doc({"doctype": "Proposal Template", "template_name": TEMPLATE})
			t.append("sections", {"proposal_section": SECTION, "sequence": 10})
			t.insert(ignore_permissions=True)
		cls.template = TEMPLATE
		frappe.db.commit()  # nosemgrep — aislar fixture

	@classmethod
	def tearDownClass(cls):
		for n in cls._quotations:
			if frappe.db.exists("Quotation", n):
				try:
					frappe.delete_doc("Quotation", n, force=True, ignore_permissions=True)
				except Exception:
					pass
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		super().tearDownClass()

	def _make(self, quotation_to="Customer", party_name=None, contact_person=None):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": quotation_to,
				"party_name": party_name or (CUSTOMER if quotation_to == "Customer" else None),
				"company": self.company,
				"currency": "MXN",
				"selling_price_list": self.price_list,
				"transaction_date": frappe.utils.today(),
				"proposal_cost_center": self.cost_center,
				"proposal_template": self.template,
				"proposal_group": f"CT-{frappe.generate_hash(length=8)}",
				"contact_person": contact_person,
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True)
		self._quotations.append(doc.name)
		return doc

	# ── nueva Quotation (before_insert) ─────────────────────────────────────────────

	def test_new_quotation_gets_customer_contact(self):
		"""Nueva Quotation dirigida a Customer (sin Deal) → contacto por defecto del Customer, persistido."""
		q = self._make()
		self.assertEqual(q.contact_person, self.contact)
		self.assertEqual(q.contact_display, "_Test Dirigido Contact")

	def test_contact_details_derived(self):
		"""email/móvil se derivan del contacto elegido (get_contact_details nativo)."""
		q = self._make()
		email, mobile = frappe.db.get_value("Contact", q.contact_person, ["email_id", "mobile_no"])
		self.assertEqual(q.contact_email, email)
		self.assertEqual(q.contact_mobile, mobile)

	# ── autocorrección en validate ──────────────────────────────────────────────────

	def test_old_draft_autocorrects_on_save(self):
		"""Draft con contact_person vacío → se autocorrige al guardar (validate), sin patch ni backfill."""
		q = self._make()
		# simular Draft histórico sin contacto (vaciar directo, sin disparar hooks)
		frappe.db.set_value(
			"Quotation", q.name, {"contact_person": "", "contact_display": ""}, update_modified=False
		)
		doc = frappe.get_doc("Quotation", q.name)
		self.assertFalse(doc.contact_person)
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.contact_person, self.contact)

	def test_existing_contact_not_overwritten_on_save(self):
		"""Si contact_person ya tiene valor, validate NO lo sobrescribe (protege selección manual)."""
		q = self._make(contact_person=self.otro)
		self.assertEqual(q.contact_person, self.otro)
		doc = frappe.get_doc("Quotation", q.name)
		doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Quotation", q.name, "contact_person"), self.otro)

	# ── no-op ───────────────────────────────────────────────────────────────────────

	def test_noop_when_not_customer(self):
		"""quotation_to != Customer → no-op."""
		if not frappe.db.exists("Lead", {"lead_name": "_Test Contact Lead"}):
			frappe.get_doc(
				{"doctype": "Lead", "lead_name": "_Test Contact Lead", "company_name": "_Test Contact Lead"}
			).insert(ignore_permissions=True)
		lead = frappe.db.get_value("Lead", {"lead_name": "_Test Contact Lead"}, "name")
		q = self._make(quotation_to="Lead", party_name=lead)
		self.assertFalse(q.get("contact_person"))

	def test_submitted_not_modified(self):
		"""La autocorrección no toca documentos no-Draft (docstatus != 0)."""
		stub = frappe._dict(docstatus=1, quotation_to="Customer", party_name=CUSTOMER)
		autocorrect_missing_contact(stub)  # guard docstatus → sin efecto, sin error
		self.assertIsNone(stub.get("contact_person"))

	# ── ruta principal: Deal → contacto del Deal prevalece (mocking, sin app crm) ─────

	def test_deal_contact_prevails_over_customer_default_on_new(self):
		"""Nueva Quotation a Customer con Deal (contacto A) y default del Customer (B) distinto →
		gana A en la creación (before_insert autoritativo); display/email/móvil derivan de A, no de B."""
		self.assertNotEqual(self.deal_contact, self.contact)  # A != B (precondición)
		with patch.object(qc, "_deal_primary_contact", return_value=self.deal_contact):
			q = self._make()
		self.assertEqual(q.contact_person, self.deal_contact)  # == A
		self.assertNotEqual(q.contact_person, self.contact)  # != B (default del Customer)
		email, mobile = frappe.db.get_value("Contact", self.deal_contact, ["email_id", "mobile_no"])
		self.assertEqual(q.contact_display, "_Test Deal A Deal")
		self.assertEqual(q.contact_email, email)
		self.assertEqual(q.contact_mobile, mobile)

	def test_deal_present_without_contact_falls_back_to_customer(self):
		"""Deal presente pero sin contacto válido → fallback al contacto default del Customer (B)."""
		with patch.object(qc, "_deal_primary_contact", return_value=None):
			q = self._make()
		self.assertEqual(q.contact_person, self.contact)  # == B (default del Customer)

	# ── prioridad interna de _deal_primary_contact (frappe.db/get_all mockeados) ──────

	@staticmethod
	def _mock_frappe(is_primary_rows, deal_contact, any_rows, contact_exists=True):
		"""Fabrica un ``frappe`` simulado para _deal_primary_contact (CRM Deal existe en el site)."""
		m = MagicMock()

		def exists(dt, name=None):
			if dt in ("DocType", "CRM Deal"):
				return True
			if dt == "Contact":
				return contact_exists
			return False

		def get_all(doctype, filters=None, pluck=None, **kw):
			if doctype != "CRM Contacts":
				return []
			return (is_primary_rows if (filters or {}).get("is_primary") == 1 else any_rows) or []

		m.db.exists.side_effect = exists
		m.get_all.side_effect = get_all
		m.db.get_value.return_value = deal_contact
		return m

	def test_deal_primary_prefers_is_primary_row(self):
		"""Fila de CRM Deal.contacts con is_primary=1 → ese contacto gana."""
		fake = self._mock_frappe(is_primary_rows=["A"], deal_contact="C", any_rows=["D"])
		with patch.object(qc, "frappe", fake):
			self.assertEqual(_deal_primary_contact("CRM-DEAL-X"), "A")

	def test_deal_primary_falls_back_to_deal_contact_field(self):
		"""Sin is_primary → fallback a CRM Deal.contact."""
		fake = self._mock_frappe(is_primary_rows=[], deal_contact="C", any_rows=["D"])
		with patch.object(qc, "frappe", fake):
			self.assertEqual(_deal_primary_contact("CRM-DEAL-X"), "C")

	def test_deal_primary_falls_back_to_first_row(self):
		"""Sin is_primary ni CRM Deal.contact → primera fila de contactos del Deal."""
		fake = self._mock_frappe(is_primary_rows=[], deal_contact=None, any_rows=["D"])
		with patch.object(qc, "frappe", fake):
			self.assertEqual(_deal_primary_contact("CRM-DEAL-X"), "D")

	def test_deal_primary_none_when_candidate_contact_missing(self):
		"""El candidato del Deal no existe como Contact → None (no se aplica un contacto fantasma)."""
		fake = self._mock_frappe(is_primary_rows=["A"], deal_contact=None, any_rows=[], contact_exists=False)
		with patch.object(qc, "frappe", fake):
			self.assertIsNone(_deal_primary_contact("CRM-DEAL-X"))

	# ── guard de la rama del Deal ────────────────────────────────────────────────────

	def test_deal_branch_guarded_without_crm(self):
		"""Sin DocType CRM Deal en el site → _deal_primary_contact devuelve None (cae al fallback)."""
		self.assertIsNone(_deal_primary_contact("CRM-DEAL-INEXISTENTE"))
