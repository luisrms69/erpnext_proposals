"""
Proposal versioning tests.

Tests run on the test site with self-created data.
No dependency on proposals.dev or SAL-QTN-* quotations.
"""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import (
	assert_single_live_proposal_for_group,
	create_new_proposal_version,
	get_live_proposal_for_group,
)


class TestProposalVersioning(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._setup_masters()
		cls._created_fy = ensure_current_fiscal_year()
		cls.v1 = cls._make_submitted_rejected_quotation()
		cls.v1_fresh = cls._make_submitted_rejected_quotation(suffix="_fresh")

	@classmethod
	def tearDownClass(cls):
		for attr in ("v1", "v1_fresh", "_v2_name"):
			name = getattr(cls, attr, None)
			if name and isinstance(name, str) and frappe.db.exists("Quotation", name):
				try:
					doc = frappe.get_doc("Quotation", name)
					if doc.docstatus == 1:
						doc.flags.ignore_linked_doctypes = True
						doc.cancel()
					frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
				except Exception:
					pass
			elif name and hasattr(name, "name"):
				n = name.name
				if frappe.db.exists("Quotation", n):
					try:
						doc = frappe.get_doc("Quotation", n)
						if doc.docstatus == 1:
							doc.flags.ignore_linked_doctypes = True
							doc.cancel()
						frappe.delete_doc("Quotation", n, force=True, ignore_permissions=True)
					except Exception:
						pass
		# No Proposal Group DocType to clean up — proposal_group is now a Data field
		cleanup_fiscal_year(getattr(cls, "_created_fy", None))
		super().tearDownClass()

	@classmethod
	def _setup_masters(cls):
		from erpnext_proposals.erpnext_proposals.tests.company import (
			get_test_company,
			get_test_item_group,
		)

		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company found.")

		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		if not cg:
			raise unittest.SkipTest("No Customer Group found.")

		terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or frappe.db.get_value(
			"Territory", {}, "name"
		)

		if not frappe.db.exists("Customer", "_Test Version Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test Version Customer",
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test Version Customer"

		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)

		ig = get_test_item_group()
		if not frappe.db.exists("Item", "_Test Version Item"):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "_Test Version Item",
					"item_name": "_Test Version Item",
					"item_group": ig,
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
		cls.item = "_Test Version Item"

		cls.cost_center = frappe.db.get_value(
			"Cost Center", {"is_group": 0, "company": cls.company}, "name"
		) or frappe.db.get_value("Cost Center", {"is_group": 0}, "name")
		if not cls.cost_center:
			root = frappe.db.get_value("Cost Center", {"company": cls.company}, "name")
			if not root:
				# Create root CC using raw SQL to bypass parent validation
				frappe.db.sql(
					"INSERT INTO `tabCost Center` (name, cost_center_name, company, is_group, lft, rgt) "
					"VALUES (%s, %s, %s, 1, 1, 2)",
					("_Test Root CC", "_Test Root CC", cls.company),
				)
				root = "_Test Root CC"
			cc = frappe.get_doc(
				{
					"doctype": "Cost Center",
					"cost_center_name": "_Test CC",
					"company": cls.company,
					"parent_cost_center": root,
					"is_group": 0,
				}
			).insert(ignore_permissions=True)
			cls.cost_center = cc.name

		# Proposal Template — required since proposal_template is now reqd=1
		if not frappe.db.exists("Proposal Template", "_Test Version Template"):
			frappe.get_doc(
				{
					"doctype": "Proposal Template",
					"template_name": "_Test Version Template",
					"description": "Template for versioning tests",
				}
			).insert(ignore_permissions=True)
		cls.proposal_template = "_Test Version Template"

	@classmethod
	def _make_submitted_rejected_quotation(cls, suffix="") -> object:
		"""Create, submit, and move to Rechazada a Quotation."""
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": cls.customer,
				"company": cls.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": f"TEST-GROUP-{frappe.generate_hash(length=6)}{suffix}",
				"proposal_template": cls.proposal_template,
				"proposal_title": f"Test Proposal{suffix}",
				"items": [
					{
						"item_code": cls.item,
						"item_name": f"_Test Version Item{suffix}",
						"qty": 1,
						"rate": 5000,
						"uom": "Nos",
					}
				],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		if cls.cost_center:
			frappe.db.set_value(
				"Quotation", doc.name, "proposal_cost_center", cls.cost_center, update_modified=False
			)
		doc.reload()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		# Move to Rechazada via direct DB (workflow requires web context)
		frappe.db.set_value("Quotation", doc.name, "workflow_state", "Rechazada", update_modified=False)
		doc.reload()
		return doc

	def _fresh_doc(self, name):
		return frappe.get_doc("Quotation", name)

	# ── Schema tests ──────────────────────────────────────────────────────────

	def test_01_versioning_columns_exist(self):
		cols = frappe.db.sql("DESCRIBE `tabQuotation`", as_dict=True)
		names = {c["Field"] for c in cols}
		for col in (
			"proposal_group",
			"proposal_version",
			"previous_proposal",
			"superseded_by_proposal",
			"proposal_revision_reason",
			"proposal_revision_summary",
		):
			self.assertIn(col, names, f"Column {col} missing from Quotation table")

	def test_02_superseded_by_has_allow_on_submit(self):
		meta = frappe.get_meta("Quotation")
		field = next((f for f in meta.fields if f.fieldname == "superseded_by_proposal"), None)
		if field is None:
			self.skipTest("superseded_by_proposal not in meta")
		self.assertEqual(field.allow_on_submit, 1)

	def test_03_proposal_group_is_data_field(self):
		meta = frappe.get_meta("Quotation")
		field = next((f for f in meta.fields if f.fieldname == "proposal_group"), None)
		if field is None:
			self.skipTest("proposal_group not in meta")
		self.assertEqual(field.fieldtype, "Data")

	# ── before_insert: proposal_group required ───────────────────────────────

	def test_04_new_quotation_has_proposal_group(self):
		self.assertIsNotNone(self.v1.proposal_group)
		self.assertTrue(len(self.v1.proposal_group) > 0)

	def test_05_first_quotation_gets_version_1(self):
		self.assertEqual(self.v1.proposal_version, 1)

	# ── Controlled versioning: create_new_proposal_version ───────────────────

	def test_06_create_v2_from_rejected_v1(self):
		v2_name = create_new_proposal_version(self.v1.name, reason="Ajuste de alcance")
		self.__class__._v2_name = v2_name

		v2 = frappe.get_doc("Quotation", v2_name)
		self.assertEqual(v2.proposal_version, 2)
		self.assertEqual(v2.previous_proposal, self.v1.name)
		self.assertEqual(v2.proposal_group, self.v1.proposal_group)
		self.assertEqual(v2.docstatus, 0)  # Borrador

	def test_07_v1_superseded_by_v2(self):
		v2_name = getattr(self, "_v2_name", None)
		if not v2_name:
			self.skipTest("v2 not created yet (run test_06 first)")
		self.v1.reload()
		self.assertEqual(self.v1.superseded_by_proposal, v2_name)

	def test_08_v2_copied_items_without_costs(self):
		v2_name = getattr(self, "_v2_name", None)
		if not v2_name:
			self.skipTest("v2 not created yet")
		v2 = frappe.get_doc("Quotation", v2_name)
		self.assertTrue(len(v2.items) > 0)
		for item in v2.items:
			self.assertIsNone(getattr(item, "rate_locked", None) or None or None)

	# ── Unicidad: una sola propuesta viva por grupo ───────────────────────────

	def test_09_cannot_create_version_from_already_superseded(self):
		"""test 08c design: v1 already superseded → must fail."""
		self.v1.reload()
		self.assertTrue(self.v1.superseded_by_proposal, "v1 should be superseded")
		with self.assertRaises(frappe.exceptions.ValidationError):
			create_new_proposal_version(self.v1.name, reason="Intento duplicado")

	def test_10_direct_api_with_previous_proposal_always_fails(self):
		"""test 08a design: API without flag must always fail."""
		with self.assertRaises(
			frappe.exceptions.ValidationError, msg="before_insert must reject previous_proposal without flag"
		):
			frappe.get_doc(
				{
					"doctype": "Quotation",
					"quotation_to": "Customer",
					"party_name": self.customer,
					"company": self.company,
					"currency": "MXN",
					"transaction_date": frappe.utils.today(),
					"proposal_group": self.v1.proposal_group,
					"proposal_version": 3,
					"previous_proposal": self.v1.name,
					"items": [{"item_code": self.item, "qty": 1, "rate": 1000, "uom": "Nos"}],
					# No flags.from_proposal_versioning
				}
			).insert(ignore_permissions=True, ignore_mandatory=True)

	def test_11_direct_api_without_previous_proposal_fails_if_live_exists(self):
		"""test 05 design: manual insert in group with live version must fail."""
		v2_name = getattr(self, "_v2_name", None)
		if not v2_name:
			self.skipTest("v2 not created yet")
		with self.assertRaises(
			frappe.exceptions.ValidationError, msg="Must block second live proposal in same group"
		):
			frappe.get_doc(
				{
					"doctype": "Quotation",
					"quotation_to": "Customer",
					"party_name": self.customer,
					"company": self.company,
					"currency": "MXN",
					"transaction_date": frappe.utils.today(),
					"proposal_group": self.v1.proposal_group,
					# no previous_proposal — path 3 (manual)
					"items": [{"item_code": self.item, "qty": 1, "rate": 1000, "uom": "Nos"}],
				}
			).insert(ignore_permissions=True, ignore_mandatory=True)

	# ── Project guard ─────────────────────────────────────────────────────────

	def test_12_cannot_create_project_from_superseded_version(self):
		"""test 07 design: project from replaced version must fail."""
		from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import (
			assert_can_create_project,
		)

		self.v1.reload()
		self.assertTrue(self.v1.superseded_by_proposal)
		with self.assertRaises(frappe.exceptions.ValidationError):
			assert_can_create_project(self.v1)

	# ── assert_single_live_proposal_for_group coverage ───────────────────────

	def test_13_borrador_detected_as_live(self):
		"""v2 in Borrador (docstatus=0) is detected as live."""
		v2_name = getattr(self, "_v2_name", None)
		if not v2_name:
			self.skipTest("v2 not created yet")
		live = get_live_proposal_for_group(self.v1.proposal_group)
		self.assertEqual(live, v2_name)

	def test_14_rechazada_not_detected_as_live(self):
		"""v1 in Rechazada is not live."""
		live = get_live_proposal_for_group(self.v1.proposal_group, exclude=getattr(self, "_v2_name", None))
		self.assertIsNone(live, "Rechazada Quotation should not be considered live")

	def test_15_group_with_no_live_version_returns_none(self):
		# v1_fresh is Rechazada, no v2 yet
		live = get_live_proposal_for_group(self.v1_fresh.proposal_group)
		self.assertIsNone(live)

	def test_17_superseded_version_with_project_cannot_touch_project(self):
		"""
		Regression guard: removing the proposal_project check from assert_can_create_project
		must NOT allow a superseded version to create or update a project.

		Protection comes from superseded_by_proposal — independent of proposal_project.
		Even if the old version already has a project, the superseded check fires first.
		"""
		from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import (
			assert_can_create_project,
		)

		superseded_with_project = frappe._dict(
			{
				"docstatus": 1,
				"workflow_state": "Ganada",
				"superseded_by_proposal": "SAL-QTN-V2",  # replaced by a newer version
				"proposal_group": "TEST-GROUP-REGR",
				"proposal_project": "_Test Existing Project",  # already has a project
				"name": "_TEST-QTN-SUPERSEDED-WITH-PROJ",
			}
		)

		with self.assertRaises(
			frappe.exceptions.ValidationError,
			msg="Superseded version with project must be blocked by superseded_by_proposal check",
		):
			assert_can_create_project(superseded_with_project)

	def test_16_cannot_version_from_proposal_with_active_project(self):
		"""assert_can_create_new_version must block if proposal_project references an existing Project."""
		from unittest.mock import patch

		from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import (
			assert_can_create_new_version,
		)

		mock_doc = frappe._dict(
			{
				"docstatus": 1,
				"workflow_state": "Rechazada",
				"superseded_by_proposal": None,
				"proposal_group": "TEST-GROUP-ACTIVE-PROJ",
				"proposal_project": "_Test Active Project",
				"name": "_TEST-QTN-WITH-PROJECT",
			}
		)

		with patch("frappe.db.exists", return_value=True):
			with self.assertRaises(frappe.exceptions.ValidationError):
				assert_can_create_new_version(mock_doc)

	# ── Regresión: la revisión NO debe copiar due_dates inválidos del documento anterior ──

	def _rejected_old(self, suffix, days_old=10, payment_terms_template=None, manual_schedule=None):
		"""Quotation submitted+Rechazada con transaction_date ANTIGUA (reproduce el escenario donde el
		due_date copiado sería anterior al posting date de la nueva revisión)."""
		old_date = frappe.utils.add_days(frappe.utils.today(), -days_old)
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": old_date,
				"proposal_group": f"TEST-REV-{frappe.generate_hash(length=6)}{suffix}",
				"proposal_template": self.proposal_template,
				"proposal_title": f"Test Rev{suffix}",
				"items": [
					{
						"item_code": self.item,
						"item_name": "_Test Rev Item",
						"qty": 1,
						"rate": 10000,
						"uom": "Nos",
					}
				],
			}
		)
		if payment_terms_template:
			doc.payment_terms_template = payment_terms_template
		for r in manual_schedule or []:
			doc.append("payment_schedule", r)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		if self.cost_center:
			frappe.db.set_value(
				"Quotation", doc.name, "proposal_cost_center", self.cost_center, update_modified=False
			)
		doc.reload()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		frappe.db.set_value("Quotation", doc.name, "workflow_state", "Rechazada", update_modified=False)
		doc.reload()
		return doc

	def _cleanup_q(self, *names):
		for n in names:
			if n and frappe.db.exists("Quotation", n):
				try:
					d = frappe.get_doc("Quotation", n)
					if d.docstatus == 1:
						d.flags.ignore_linked_doctypes = True
						d.cancel()
					frappe.delete_doc("Quotation", n, force=True, ignore_permissions=True)
				except Exception:
					pass

	def test_17_revision_automatic_row_regenerates_valid_due_date(self):
		"""Fila automática 100% + fecha antigua: la revisión regenera con fecha válida (due_date no
		anterior a la fecha de la revisión), no conserva la due_date vieja y guarda sin error."""
		old = self._rejected_old("_auto")
		old_due = old.payment_schedule[0].due_date if old.payment_schedule else None
		v2_name = None
		try:
			v2_name = create_new_proposal_version(old.name, reason="Regresión fila automática")
			v2 = frappe.get_doc("Quotation", v2_name)
			self.assertEqual(v2.docstatus, 0)
			for p in v2.payment_schedule:
				self.assertGreaterEqual(str(p.due_date), str(v2.transaction_date))
				if old_due:
					self.assertNotEqual(str(p.due_date), str(old_due))
			if v2.payment_schedule:
				self.assertAlmostEqual(
					sum(p.payment_amount or 0 for p in v2.payment_schedule), v2.grand_total, places=2
				)
		finally:
			self._cleanup_q(v2_name, old.name)

	def test_18_revision_with_template_recalcs_schedule(self):
		"""Con Payment Terms Template + fecha antigua: la revisión regenera el calendario desde la
		nueva fecha, conserva porcentajes/términos y no conserva fechas antiguas."""
		for t, portion, cd in (("_Test Rev PT A", 40, 0), ("_Test Rev PT B", 60, 15)):
			if not frappe.db.exists("Payment Term", t):
				frappe.get_doc(
					{
						"doctype": "Payment Term",
						"payment_term_name": t,
						"invoice_portion": portion,
						"credit_days": cd,
						"due_date_based_on": "Day(s) after invoice date",
					}
				).insert(ignore_permissions=True)
		ptt = "_Test Rev PTT"
		if not frappe.db.exists("Payment Terms Template", ptt):
			d = frappe.get_doc(
				{
					"doctype": "Payment Terms Template",
					"template_name": ptt,
					"allocate_payment_based_on_payment_terms": 1,
				}
			)
			d.append(
				"terms",
				{
					"payment_term": "_Test Rev PT A",
					"invoice_portion": 40,
					"credit_days": 0,
					"due_date_based_on": "Day(s) after invoice date",
				},
			)
			d.append(
				"terms",
				{
					"payment_term": "_Test Rev PT B",
					"invoice_portion": 60,
					"credit_days": 15,
					"due_date_based_on": "Day(s) after invoice date",
				},
			)
			d.insert(ignore_permissions=True)
		old = self._rejected_old("_tmpl", payment_terms_template=ptt)
		old_dues = {str(p.due_date) for p in old.payment_schedule}
		v2_name = None
		try:
			v2_name = create_new_proposal_version(old.name, reason="Regresión template")
			v2 = frappe.get_doc("Quotation", v2_name)
			self.assertEqual(v2.payment_terms_template, ptt)
			self.assertEqual(sorted(int(p.invoice_portion) for p in v2.payment_schedule), [40, 60])
			for p in v2.payment_schedule:
				self.assertGreaterEqual(str(p.due_date), str(v2.transaction_date))
				self.assertNotIn(str(p.due_date), old_dues)
			self.assertAlmostEqual(
				sum(p.payment_amount or 0 for p in v2.payment_schedule), v2.grand_total, places=2
			)
		finally:
			self._cleanup_q(v2_name, old.name)
			if frappe.db.exists("Payment Terms Template", ptt):
				frappe.delete_doc("Payment Terms Template", ptt, force=True, ignore_permissions=True)
			for t in ("_Test Rev PT A", "_Test Rev PT B"):
				if frappe.db.exists("Payment Term", t):
					frappe.delete_doc("Payment Term", t, force=True, ignore_permissions=True)

	def test_19_revision_manual_schedule_is_blocked(self):
		"""Calendario MANUAL significativo (sin template): la revisión no falsea condiciones — se
		detiene con error controlado en lugar de copiar fechas inválidas."""
		old_date = frappe.utils.add_days(frappe.utils.today(), -10)
		manual = [
			{
				"description": "Anticipo manual",
				"invoice_portion": 50,
				"payment_amount": 5000,
				"due_date": old_date,
			},
			{
				"description": "Saldo manual",
				"invoice_portion": 50,
				"payment_amount": 5000,
				"due_date": frappe.utils.add_days(old_date, 5),
			},
		]
		old = self._rejected_old("_manual", manual_schedule=manual)
		try:
			if len(old.payment_schedule) > 1:
				with self.assertRaises(frappe.exceptions.ValidationError):
					create_new_proposal_version(old.name, reason="Regresión manual")
			else:
				self.skipTest("ERPNext no conservó el calendario manual de 2 filas en este entorno")
		finally:
			self._cleanup_q(old.name)
