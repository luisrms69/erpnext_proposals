"""
Proposal versioning tests.

Tests run on the test site with self-created data.
No dependency on proposals.dev or SAL-QTN-* quotations.
"""

import unittest

import frappe
from frappe.utils import flt

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
		cls._extra = []  # Quotations creadas por tests B3 (limpieza en tearDownClass)
		cls.v1 = cls._make_submitted_rejected_quotation()
		cls.v1_fresh = cls._make_submitted_rejected_quotation(suffix="_fresh")

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

		# Items para Required Items (sin Scope Items de catálogo → no generan scope ejecutable). B3.
		for code in ("_Test Version Req A", "_Test Version Req B"):
			if not frappe.db.exists("Item", code):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_name": code,
						"item_group": ig,
						"stock_uom": "Nos",
						"is_stock_item": 0,
					}
				).insert(ignore_permissions=True)
		cls.req_a = "_Test Version Req A"
		cls.req_b = "_Test Version Req B"

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

	# ── B3 helper: Rechazada submitted con Required Items ──────────────────────
	def _rejected_with_required(self, required):
		"""Quotation submitted+Rechazada con Required Items (input semántico + snapshots congelados por el
		freeze del submit). `required` = lista de (item, qty)."""
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": f"TEST-REQ-{frappe.generate_hash(length=6)}",
				"proposal_template": self.proposal_template,
				"proposal_title": "Test Req Proposal",
				"items": [
					{"item_code": self.item, "item_name": self.item, "qty": 1, "rate": 5000, "uom": "Nos"}
				],
				"required_items": [{"item": it, "qty": q, "uom": "Nos"} for (it, q) in required],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._extra.append(doc.name)
		if self.cost_center:
			frappe.db.set_value(
				"Quotation", doc.name, "proposal_cost_center", self.cost_center, update_modified=False
			)
		doc.reload()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()  # before_submit → freeze → congela frozen_cost_rate/cost_locked/economic_behavior
		frappe.db.set_value("Quotation", doc.name, "workflow_state", "Rechazada", update_modified=False)
		return frappe.get_doc("Quotation", doc.name)

	def _version_of(self, old_name, reason="Regresión Required Items B3"):
		v2_name = create_new_proposal_version(old_name, reason=reason)
		self.__class__._extra.append(v2_name)
		return frappe.get_doc("Quotation", v2_name)

	# ── B3: required_items preservados al versionar (ADR-0019 §7.4) ────────────
	def test_b3_01_required_items_preserved_semantics(self):
		"""#1 La nueva versión conserva nº de filas + item/qty/uom/auto_generated."""
		old = self._rejected_with_required([(self.req_a, 3)])
		self.assertEqual(len(old.required_items), 1)
		v2 = self._version_of(old.name)
		self.assertEqual(len(v2.required_items), 1, "misma cantidad de Required Items")
		r = v2.required_items[0]
		self.assertEqual(r.item, self.req_a)
		self.assertEqual(r.qty, 3)
		self.assertEqual(r.uom, "Nos")
		self.assertEqual(r.auto_generated, old.required_items[0].auto_generated, "auto_generated se conserva")

	def test_b3_02_multiple_required_items_preserved(self):
		"""#2 Multiplicidad y valores de cada fila se conservan."""
		old = self._rejected_with_required([(self.req_a, 2), (self.req_b, 5)])
		v2 = self._version_of(old.name)
		by_item = {r.item: r for r in v2.required_items}
		self.assertEqual(set(by_item), {self.req_a, self.req_b})
		self.assertEqual(by_item[self.req_a].qty, 2)
		self.assertEqual(by_item[self.req_b].qty, 5)

	def test_b3_03_frozen_snapshot_not_inherited(self):
		"""#3 El snapshot económico anterior NO se hereda: la nueva versión nace en Borrador."""
		old = self._rejected_with_required([(self.req_a, 1)])
		# La versión anterior (submitted) SÍ tiene snapshot congelado.
		self.assertTrue(old.required_items[0].cost_locked, "precondición: la anterior está congelada")
		v2 = self._version_of(old.name)
		r = v2.required_items[0]
		self.assertFalse(r.cost_locked, "cost_locked no se hereda")
		self.assertIn(flt(r.frozen_cost_rate), (0.0,), "frozen_cost_rate no se hereda")
		self.assertFalse(r.frozen_cost_source, "frozen_cost_source no se hereda")
		self.assertFalse(r.economic_behavior, "economic_behavior no se hereda")
		self.assertFalse(r.billing_interval, "billing_interval no se hereda")
		self.assertFalse(r.billing_interval_count, "billing_interval_count no se hereda")

	def test_b3_04_refreeze_on_formalization_repopulates(self):
		"""#4 Al re-formalizar (submit → freeze) los snapshots vuelven a poblarse y
		assert_economic_snapshot_complete sigue pasando (no lanza)."""
		old = self._rejected_with_required([(self.req_a, 1)])
		v2 = self._version_of(old.name)
		v2.flags.ignore_mandatory = True
		v2.flags.ignore_links = True
		v2.submit()  # before_submit → freeze + assert_economic_snapshot_complete (lanzaría si incompleto)
		v2.reload()
		r = v2.required_items[0]
		self.assertTrue(r.cost_locked, "el freeze recongela cost_locked")
		self.assertTrue(r.economic_behavior, "el freeze recongela economic_behavior")

	def test_b3_05_no_required_items_unchanged(self):
		"""#5 Versión sin Required Items: comportamiento intacto (0 filas, sin error)."""
		old = self._rejected_with_required([])  # rechazada dedicada, sin Required Items
		v2 = self._version_of(old.name, reason="Regresión sin required B3")
		self.assertEqual(list(v2.get("required_items") or []), [])

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

	# ── Issue #17: proposal_group se toma de crm_deal si no hay grupo manual ──

	def setUp(self):
		if not hasattr(self, "_i17_created"):
			self._i17_created = []

	def tearDown(self):
		for n in getattr(self, "_i17_created", []):
			if frappe.db.exists("Quotation", n):
				try:
					frappe.delete_doc("Quotation", n, force=True, ignore_permissions=True)
				except Exception:
					pass
		self._i17_created = []

	def _make_draft(self, proposal_group=None, crm_deal=None):
		"""Crea una Quotation Draft. `crm_deal` (campo del app CRM, ausente en el site de tests) se
		pasa como atributo del doc; el hook lo lee con doc.get(...) igual que en un site con CRM."""
		spec = {
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": self.customer,
			"company": self.company,
			"currency": "MXN",
			"transaction_date": frappe.utils.today(),
			"proposal_template": self.proposal_template,
			"proposal_title": "Issue17",
			"items": [
				{
					"item_code": self.item,
					"item_name": "_Test Version Item",
					"qty": 1,
					"rate": 5000,
					"uom": "Nos",
				}
			],
		}
		if proposal_group is not None:
			spec["proposal_group"] = proposal_group
		if crm_deal is not None:
			spec["crm_deal"] = crm_deal
		doc = frappe.get_doc(spec)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self._i17_created.append(doc.name)
		return doc

	def test_17a_manual_group_preserved_over_crm_deal(self):
		"""1) Si proposal_group ya tiene valor, se conserva aunque venga crm_deal."""
		g = f"MANUAL-{frappe.generate_hash(length=6)}"
		doc = self._make_draft(proposal_group=g, crm_deal="CRM-DEAL-9999")
		self.assertEqual(doc.proposal_group, g)

	def test_17b_crm_deal_copied_when_group_empty(self):
		"""2) proposal_group vacío + crm_deal presente → se copia exactamente crm_deal (sin transformar)."""
		deal = f"CRM-DEAL-{frappe.generate_hash(length=6)}"
		doc = self._make_draft(proposal_group=None, crm_deal=deal)
		self.assertEqual(doc.proposal_group, deal)

	def test_17c_both_empty_still_raises(self):
		"""3) Sin proposal_group ni crm_deal → se mantiene el error obligatorio actual."""
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._make_draft(proposal_group=None, crm_deal=None)

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
