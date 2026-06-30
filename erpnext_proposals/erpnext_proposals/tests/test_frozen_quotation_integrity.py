"""
Frozen Quotation integrity test.

Creates a Quotation with known prices, submits it, then attempts to
modify prices and verifies the PDF still reflects the original data.

Two scenarios tested:
A. Application-layer change (doc.save() with modified rate)
   → must raise UpdateAfterSubmitError / ValidationError
   → PDF must show original price

B. Direct DB change (frappe.db.set_value bypassing validation)
   → documents the vulnerability: direct DB writes CAN change displayed data
   → this is why the PDF attachment at freeze time is the authoritative record
"""

import unittest

import frappe
from frappe.exceptions import UpdateAfterSubmitError

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)

ORIGINAL_RATE = 5_000.0
MODIFIED_RATE = 9_999.0


class TestFrozenQuotationIntegrity(unittest.TestCase):
	# ── Setup ──────────────────────────────────────────────────────────────────

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._setup_master_data()
		cls._created_fy = ensure_current_fiscal_year()
		cls.quotation = cls._create_and_submit_quotation()

	@classmethod
	def tearDownClass(cls):
		name = getattr(getattr(cls, "quotation", None), "name", None)
		if name and frappe.db.exists("Quotation", name):
			try:
				doc = frappe.get_doc("Quotation", name)
				if doc.docstatus == 1:
					doc.flags.ignore_linked_doctypes = True
					doc.cancel()
				frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
			except Exception:
				pass
		cleanup_fiscal_year(getattr(cls, "_created_fy", None))
		super().tearDownClass()

	@classmethod
	def _setup_master_data(cls):
		# Use any existing company — ERPNext test site always has at least one
		cls.company = frappe.db.get_value("Company", {}, "name")
		if not cls.company:
			raise unittest.SkipTest("No Company found on test site — run bench migrate first.")

		# Use any existing Customer Group (non-group)
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		if not cg:
			raise unittest.SkipTest("No Customer Group found. Run ci_pre_tests first.")

		terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or frappe.db.get_value(
			"Territory", {}, "name"
		)

		# Customer
		if not frappe.db.exists("Customer", "_Test Integrity Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test Integrity Customer",
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test Integrity Customer"

		# UOM
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)

		# Item
		ig = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or frappe.db.get_value(
			"Item Group", {}, "name"
		)
		if not frappe.db.exists("Item", "_Test Integrity Item"):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "_Test Integrity Item",
					"item_name": "_Test Integrity Item",
					"item_group": ig,
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
		cls.item = "_Test Integrity Item"

		# Cost center — look for any existing one (company-agnostic for test site)
		cls.cost_center = frappe.db.get_value(
			"Cost Center", {"is_group": 0, "company": cls.company}, "name"
		) or frappe.db.get_value("Cost Center", {"is_group": 0}, "name")

	@classmethod
	def _create_and_submit_quotation(cls):
		"""Create a Quotation with a known rate and submit it."""
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": cls.customer,
				"proposal_group": "TEST-" + frappe.generate_hash(length=8),
				"company": cls.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"items": [
					{
						"item_code": cls.item,
						"item_name": "_Test Integrity Item",
						"qty": 2,
						"rate": ORIGINAL_RATE,
						"uom": "Nos",
					}
				],
			}
		)
		# ignore_mandatory=True on insert so cost_center absence doesn't block
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		# Set cost_center directly before submit
		frappe.db.set_value(
			"Quotation",
			doc.name,
			"proposal_cost_center",
			cls.cost_center or "Main - _TPC",
			update_modified=False,
		)
		doc.reload()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		return doc

	# ── Helpers ────────────────────────────────────────────────────────────────

	def _get_fresh_doc(self):
		return frappe.get_doc("Quotation", self.quotation.name)

	def _pdf_html(self):
		return frappe.get_print("Quotation", self.quotation.name, print_format="Propuesta Comercial")

	def _rate_in_pdf(self, rate):
		return f"{rate:,.2f}" in self._pdf_html()

	# ── Tests ──────────────────────────────────────────────────────────────────

	def test_01_quotation_is_submitted(self):
		doc = self._get_fresh_doc()
		self.assertEqual(doc.docstatus, 1, "Quotation must be submitted (docstatus=1)")
		self.assertEqual(doc.items[0].rate, ORIGINAL_RATE)

	def test_02_original_price_appears_in_pdf(self):
		self.assertTrue(
			self._rate_in_pdf(ORIGINAL_RATE),
			f"Original rate {ORIGINAL_RATE:,.2f} must appear in PDF",
		)

	def test_03_app_layer_rejects_rate_change(self):
		"""doc.save() with a modified rate must raise an error."""
		doc = self._get_fresh_doc()
		doc.items[0].rate = MODIFIED_RATE

		with self.assertRaises(
			(UpdateAfterSubmitError, frappe.exceptions.ValidationError),
			msg="Saving a submitted Quotation with modified rate must raise an error",
		):
			doc.save()

		# Confirm rate not persisted
		doc.reload()
		self.assertEqual(
			doc.items[0].rate,
			ORIGINAL_RATE,
			"Rate must remain unchanged after rejected save",
		)

	def test_04_pdf_still_shows_original_price_after_rejected_save(self):
		"""After the rejected save in test_03, the PDF must still show original price."""
		self.assertTrue(
			self._rate_in_pdf(ORIGINAL_RATE),
			f"PDF must still show original rate {ORIGINAL_RATE:,.2f} after rejected save",
		)
		self.assertFalse(
			self._rate_in_pdf(MODIFIED_RATE),
			f"PDF must NOT show modified rate {MODIFIED_RATE:,.2f}",
		)

	def test_05_grand_total_matches_document(self):
		doc = self._get_fresh_doc()
		html = self._pdf_html()
		expected = f"{doc.grand_total:,.2f}"
		self.assertIn(
			expected,
			html,
			f"grand_total {expected} must appear in PDF",
		)

	def test_06_item_name_appears_in_pdf(self):
		html = self._pdf_html()
		self.assertIn(
			"_Test Integrity Item",
			html,
			"Item name must appear in PDF",
		)

	def test_07_direct_db_write_vulnerability_is_documented(self):
		"""
		frappe.db.set_value bypasses allow_on_submit validation.
		This test documents that direct DB writes CAN change displayed data.

		Implication: the PDF ATTACHMENT generated at freeze time is the only
		authoritative record. A regenerated PDF after a direct DB modification
		will reflect the modified data.

		Mitigation: only grant direct DB write access to trusted administrators.
		The application layer (UI, API) is fully protected.
		"""
		doc = self._get_fresh_doc()
		item_row_name = doc.items[0].name
		original_rate = doc.items[0].rate

		try:
			# Direct DB write — bypasses allow_on_submit
			frappe.db.set_value(
				"Quotation Item",
				item_row_name,
				"rate",
				MODIFIED_RATE,
				update_modified=False,
			)
			frappe.db.commit()  # nosemgrep

			doc.reload()
			# PDF will show modified rate — this is the documented vulnerability
			html = self._pdf_html()
			rate_changed_in_pdf = f"{MODIFIED_RATE:,.2f}" in html

			# We assert TRUE here to document that the vulnerability exists
			# If this ever becomes FALSE it means we added DB-level protection
			self.assertTrue(
				rate_changed_in_pdf,
				"KNOWN VULNERABILITY: direct frappe.db.set_value bypasses allow_on_submit. "
				"The PDF attachment at freeze time is the only authoritative record.",
			)

		finally:
			# Always restore original rate
			frappe.db.set_value(
				"Quotation Item",
				item_row_name,
				"rate",
				original_rate,
				update_modified=False,
			)
			frappe.db.commit()  # nosemgrep
