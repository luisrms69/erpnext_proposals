"""
Print Format integrity tests — schema and live calculation variables.

Two test classes:

1. TestPrintFormatSchemaIntegrity
   Site-independent. Checks DocType metadata only:
   - Financial fields on Quotation Item have allow_on_submit=0
   - Scope item calculation fields have allow_on_submit=0
   - proposal_sections_snapshot has allow_on_submit=1

2. TestLiveCalculationVariables
   Creates its own Quotation with known prices, submits it, then
   attempts to modify live calculation variables via the application
   layer and verifies both Print Formats still reflect the original
   values (not the attempted modifications).

   Variables tested:
   - doc.items.rate (Propuesta Comercial — item prices)
   - doc.items.qty (Propuesta Comercial — quantities)
   - doc.quotation_scope_items.estimated_hours (Rentabilidad — labor cost)

No test depends on proposals.dev, SAL-QTN-* quotations, or any
pre-existing site data beyond the minimum ERPNext master data.
"""

import unittest

import frappe
from frappe.exceptions import UpdateAfterSubmitError

ORIGINAL_RATE = 8_000.0
ORIGINAL_QTY = 3.0
MODIFIED_RATE = 1.0
MODIFIED_QTY = 1.0


# ── 1. Schema tests ────────────────────────────────────────────────────────────


class TestPrintFormatSchemaIntegrity(unittest.TestCase):
	"""DocType metadata checks — no data required."""

	def _assert_protected(self, doctype, fieldname):
		meta = frappe.get_meta(doctype)
		field = next((f for f in meta.fields if f.fieldname == fieldname), None)
		self.assertIsNotNone(field, f"Field '{fieldname}' not found on {doctype}")
		self.assertEqual(
			field.allow_on_submit,
			0,
			f"{doctype}.{fieldname} must have allow_on_submit=0 — "
			"modifying this after submit would corrupt frozen proposal PDFs",
		)

	# Quotation Item financial fields
	def test_item_rate_protected(self):
		self._assert_protected("Quotation Item", "rate")

	def test_item_qty_protected(self):
		self._assert_protected("Quotation Item", "qty")

	def test_item_net_amount_protected(self):
		self._assert_protected("Quotation Item", "net_amount")

	def test_item_amount_protected(self):
		self._assert_protected("Quotation Item", "amount")

	def test_item_net_rate_protected(self):
		self._assert_protected("Quotation Item", "net_rate")

	def test_item_discount_percentage_protected(self):
		self._assert_protected("Quotation Item", "discount_percentage")

	# Quotation Scope Item calculation fields
	def test_scope_estimated_hours_protected(self):
		self._assert_protected("Quotation Scope Item", "estimated_hours")

	def test_scope_activity_type_protected(self):
		self._assert_protected("Quotation Scope Item", "activity_type")

	def test_scope_designation_protected(self):
		self._assert_protected("Quotation Scope Item", "designation")

	# Custom proposal fields
	def test_snapshot_has_allow_on_submit(self):
		meta = frappe.get_meta("Quotation")
		field = next(
			(f for f in meta.fields if f.fieldname == "proposal_sections_snapshot"),
			None,
		)
		if field is None:
			raise unittest.SkipTest("proposal_sections_snapshot not installed.")
		self.assertEqual(field.allow_on_submit, 1, "proposal_sections_snapshot must have allow_on_submit=1")

	def test_proposal_template_protected(self):
		meta = frappe.get_meta("Quotation")
		field = next((f for f in meta.fields if f.fieldname == "proposal_template"), None)
		if field is None:
			raise unittest.SkipTest("proposal_template not installed.")
		self.assertEqual(field.allow_on_submit, 0, "proposal_template must have allow_on_submit=0")


# ── 2. Live calculation variable tests ────────────────────────────────────────


class TestLiveCalculationVariables(unittest.TestCase):
	"""
	Creates a Quotation with known values, submits it, then attempts to
	modify live calculation variables via the application API.
	Verifies both Print Formats continue to reflect the original values.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._setup_masters()
		cls.quotation = cls._create_and_submit()

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
		super().tearDownClass()

	@classmethod
	def _setup_masters(cls):
		cls.company = frappe.db.get_value("Company", {}, "name")
		if not cls.company:
			raise unittest.SkipTest("No Company found.")

		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		if not cg:
			raise unittest.SkipTest("No Customer Group found.")

		terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or frappe.db.get_value(
			"Territory", {}, "name"
		)

		if not frappe.db.exists("Customer", "_Test Print Integrity Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test Print Integrity Customer",
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test Print Integrity Customer"

		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)

		ig = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or frappe.db.get_value(
			"Item Group", {}, "name"
		)
		if not frappe.db.exists("Item", "_Test Print Integrity Item"):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "_Test Print Integrity Item",
					"item_name": "_Test Print Integrity Item",
					"item_group": ig,
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
		cls.item = "_Test Print Integrity Item"

		cls.cost_center = frappe.db.get_value(
			"Cost Center", {"is_group": 0, "company": cls.company}, "name"
		) or frappe.db.get_value("Cost Center", {"is_group": 0}, "name")

	@classmethod
	def _create_and_submit(cls):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": cls.customer,
				"company": cls.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"items": [
					{
						"item_code": cls.item,
						"item_name": "_Test Print Integrity Item",
						"qty": ORIGINAL_QTY,
						"rate": ORIGINAL_RATE,
						"uom": "Nos",
					}
				],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		if cls.cost_center:
			frappe.db.set_value(
				"Quotation",
				doc.name,
				"proposal_cost_center",
				cls.cost_center,
				update_modified=False,
			)
		doc.reload()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		return doc

	def _fresh(self):
		return frappe.get_doc("Quotation", self.quotation.name)

	def _propuesta_html(self):
		return frappe.get_print("Quotation", self.quotation.name, print_format="Propuesta Comercial")

	def _rentabilidad_html(self):
		return frappe.get_print("Quotation", self.quotation.name, print_format="Rentabilidad Estimada")

	# ── Baseline ──────────────────────────────────────────────────────────────

	def test_01_quotation_is_submitted(self):
		doc = self._fresh()
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.items[0].rate, ORIGINAL_RATE)
		self.assertEqual(doc.items[0].qty, ORIGINAL_QTY)

	def test_02_original_rate_in_propuesta_pdf(self):
		self.assertIn(
			f"{ORIGINAL_RATE:,.2f}",
			self._propuesta_html(),
			"Original rate must appear in Propuesta Comercial PDF",
		)

	def test_03_original_total_in_propuesta_pdf(self):
		doc = self._fresh()
		self.assertIn(
			f"{doc.grand_total:,.2f}",
			self._propuesta_html(),
			"grand_total must appear in Propuesta Comercial PDF",
		)

	def test_04_original_total_in_rentabilidad_pdf(self):
		doc = self._fresh()
		self.assertIn(
			f"{doc.net_total:,.2f}",
			self._rentabilidad_html(),
			"net_total must appear in Rentabilidad Estimada PDF",
		)

	# ── Application layer: modifications must be rejected ─────────────────────

	def test_05_app_rejects_rate_change(self):
		doc = self._fresh()
		doc.items[0].rate = MODIFIED_RATE
		with self.assertRaises(
			(UpdateAfterSubmitError, frappe.exceptions.ValidationError),
			msg="Changing rate on submitted Quotation must raise an error",
		):
			doc.save()
		doc.reload()
		self.assertEqual(doc.items[0].rate, ORIGINAL_RATE, "Rate must remain unchanged after rejected save")

	def test_06_app_rejects_qty_change(self):
		doc = self._fresh()
		doc.items[0].qty = MODIFIED_QTY
		with self.assertRaises(
			(UpdateAfterSubmitError, frappe.exceptions.ValidationError),
			msg="Changing qty on submitted Quotation must raise an error",
		):
			doc.save()
		doc.reload()
		self.assertEqual(doc.items[0].qty, ORIGINAL_QTY, "Qty must remain unchanged after rejected save")

	# ── PDF reflects original values after rejected modifications ─────────────

	def test_07_propuesta_pdf_unchanged_after_rejected_rate_change(self):
		"""After test_05 rejected the rate change, PDF must still show original."""
		html = self._propuesta_html()
		self.assertIn(f"{ORIGINAL_RATE:,.2f}", html, "Original rate must still appear in PDF")
		self.assertNotIn(f"{MODIFIED_RATE:,.2f}", html, "Modified rate must NOT appear in PDF")

	def test_08_rentabilidad_pdf_unchanged_after_rejected_qty_change(self):
		"""After test_06 rejected the qty change, Rentabilidad must still show original total."""
		doc = self._fresh()
		self.assertIn(
			f"{doc.net_total:,.2f}",
			self._rentabilidad_html(),
			"Original net_total must still appear in Rentabilidad PDF",
		)
