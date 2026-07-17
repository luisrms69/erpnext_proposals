"""TASK 6 — Resolución, validación y congelamiento del Print Format comercial.

Casos: A default · B template · C override · D congelamiento inmutable · E nueva versión ·
F formato inválido · G Rentabilidad independiente.
"""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.tests.phases import cleanup_test_phases, ensure_test_phases
from erpnext_proposals.erpnext_proposals.utils.print_format import (
	DEFAULT_COMMERCIAL_PRINT_FORMAT,
	dynamic_commercial_print_format,
	resolve_commercial_print_format,
	validate_print_format,
)

ALT = "Test Proposal Alternate Format"
TPL_PF = "_Test PF Template WithFormat"
TPL_NOPF = "_Test PF Template NoFormat"
SECTION = "_Test PF Section"
SCOPE = "_TEST_PF_SCOPE"


class TestPrintFormatResolution(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_value("Company", {}, "name")
		if not cls.company:
			raise unittest.SkipTest("No Company on test site.")
		cls._fy = ensure_current_fiscal_year()
		cls._phases = ensure_test_phases()

		_ensure(
			"Print Format",
			ALT,
			{
				"doctype": "Print Format",
				"name": ALT,
				"doc_type": "Quotation",
				"standard": "No",
				"print_format_type": "Jinja",
				"html": "<div>ALT {{ doc.name }}</div>",
				"disabled": 0,
			},
		)
		_ensure(
			"Print Format",
			"_Test PF Wrong Doctype",
			{
				"doctype": "Print Format",
				"name": "_Test PF Wrong Doctype",
				"doc_type": "User",
				"standard": "No",
				"print_format_type": "Jinja",
				"html": "x",
			},
		)
		_ensure(
			"Print Format",
			"_Test PF Disabled",
			{
				"doctype": "Print Format",
				"name": "_Test PF Disabled",
				"doc_type": "Quotation",
				"standard": "No",
				"print_format_type": "Jinja",
				"html": "x",
				"disabled": 1,
			},
		)
		_ensure(
			"Proposal Section",
			SECTION,
			{
				"doctype": "Proposal Section",
				"section_name": SECTION,
				"title": "Sec",
				"content": "<p>x</p>",
				"enabled": 1,
			},
		)
		if not frappe.db.exists("Proposal Template", TPL_PF):
			t = frappe.get_doc({"doctype": "Proposal Template", "template_name": TPL_PF, "print_format": ALT})
			t.append("sections", {"proposal_section": SECTION, "sequence": 10, "include_by_default": 1})
			t.insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TPL_NOPF):
			t = frappe.get_doc({"doctype": "Proposal Template", "template_name": TPL_NOPF})
			t.append("sections", {"proposal_section": SECTION, "sequence": 10, "include_by_default": 1})
			t.insert(ignore_permissions=True)

		cls.customer = _ensure_customer()
		cls.item = _ensure_item()
		cls.cost_center = frappe.db.get_value("Cost Center", {"is_group": 0, "company": cls.company}, "name")
		_ensure(
			"Scope Item",
			SCOPE,
			{
				"doctype": "Scope Item",
				"code": SCOPE,
				"title": "Act",
				"sequence": 10,
				"phase": "DISC",
				"estimated_hours": 8,
				"erpnext_item": cls.item,
				"enabled": 1,
				"visible_in_proposal": 1,
			},
		)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		cleanup_test_phases(getattr(cls, "_phases", None))
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		super().tearDownClass()

	# ── A / B / C — resolución dinámica (Borrador) ────────────────────────────
	def test_A_default(self):
		doc = frappe._dict({"proposal_template": TPL_NOPF})
		self.assertEqual(resolve_commercial_print_format(doc), DEFAULT_COMMERCIAL_PRINT_FORMAT)

	def test_B_template(self):
		doc = frappe._dict({"proposal_template": TPL_PF})
		self.assertEqual(resolve_commercial_print_format(doc), ALT)

	def test_C_override_priority(self):
		doc = frappe._dict(
			{"proposal_template": TPL_PF, "proposal_print_format": DEFAULT_COMMERCIAL_PRINT_FORMAT}
		)
		self.assertEqual(resolve_commercial_print_format(doc), DEFAULT_COMMERCIAL_PRINT_FORMAT)

	def test_frozen_takes_priority(self):
		doc = frappe._dict(
			{
				"proposal_template": TPL_PF,
				"proposal_print_format": ALT,
				"proposal_effective_print_format": DEFAULT_COMMERCIAL_PRINT_FORMAT,
			}
		)
		self.assertEqual(resolve_commercial_print_format(doc), DEFAULT_COMMERCIAL_PRINT_FORMAT)

	# ── F — formato inválido ──────────────────────────────────────────────────
	def test_F_invalid_doctype(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			validate_print_format("_Test PF Wrong Doctype")

	def test_F_disabled(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			validate_print_format("_Test PF Disabled")

	def test_F_missing(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			validate_print_format("_PF_que_no_existe_123")

	def test_valid_passes(self):
		validate_print_format(ALT)  # no raise
		validate_print_format(None)  # opcional

	# ── D — congelamiento e inmutabilidad ─────────────────────────────────────
	def test_D_freeze_persists_and_immutable(self):
		q = self._submit_proposal(TPL_PF)
		try:
			self.assertEqual(
				q.proposal_effective_print_format, ALT, "efectivo congelado = formato del template"
			)
			# cambiar el default del template → no debe afectar la congelada
			frappe.db.set_value("Proposal Template", TPL_PF, "print_format", DEFAULT_COMMERCIAL_PRINT_FORMAT)
			fresh = frappe.get_doc("Quotation", q.name)
			self.assertEqual(fresh.proposal_effective_print_format, ALT)
			self.assertEqual(resolve_commercial_print_format(fresh), ALT)
		finally:
			frappe.db.set_value("Proposal Template", TPL_PF, "print_format", ALT)
			_cancel_delete(q.name)

	# ── E — nueva versión hereda, editable ────────────────────────────────────
	def test_E_new_version_inherits(self):
		q = self._submit_proposal(TPL_PF)
		v2name = None
		try:
			frappe.db.set_value("Quotation", q.name, "workflow_state", "Rechazada")
			from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import (
				create_new_proposal_version,
			)

			v2name = create_new_proposal_version(q.name, reason="test", summary="")
			v2 = frappe.get_doc("Quotation", v2name)
			self.assertEqual(v2.proposal_print_format, ALT, "v2 hereda el formato como override editable")
			self.assertFalse(v2.proposal_effective_print_format, "v2 no copia el congelado")
			self.assertEqual(int(v2.docstatus), 0, "v2 en Borrador editable")
			# v1 intacta
			self.assertEqual(frappe.db.get_value("Quotation", q.name, "proposal_effective_print_format"), ALT)
		finally:
			if v2name:
				_cancel_delete(v2name)
			_cancel_delete(q.name)

	# ── G — Rentabilidad independiente del formato comercial ──────────────────
	def test_G_rentabilidad_independiente(self):
		doc = frappe._dict({"proposal_template": TPL_PF, "proposal_print_format": ALT})
		self.assertEqual(resolve_commercial_print_format(doc), ALT)
		self.assertNotEqual(resolve_commercial_print_format(doc), "Rentabilidad Estimada")
		self.assertNotEqual(dynamic_commercial_print_format(doc), "Rentabilidad Estimada")

	# ── helper ────────────────────────────────────────────────────────────────
	def _submit_proposal(self, template):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": f"TEST-PF-{frappe.generate_hash(length=6)}",
				"proposal_template": template,
				"proposal_title": "PF Test",
				"proposal_cost_center": self.cost_center,
				"items": [{"item_code": self.item, "qty": 1, "rate": 5000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		doc.reload()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		doc.reload()
		return doc


def _ensure(dt, name, values):
	if not frappe.db.exists(dt, name):
		frappe.get_doc(values).insert(ignore_permissions=True)


def _ensure_customer():
	name = "_Test PF Customer"
	if not frappe.db.exists("Customer", name):
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {}, "name")
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_type": "Company",
				"customer_group": cg,
				"territory": terr,
			}
		).insert(ignore_permissions=True)
	return name


def _ensure_item():
	name = "_Test PF Item"
	if not frappe.db.exists("UOM", "Nos"):
		frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
	if not frappe.db.exists("Item", name):
		ig = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or frappe.db.get_value(
			"Item Group", {}, "name"
		)
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": name,
				"item_name": name,
				"item_group": ig,
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)
	return name


def _cancel_delete(name):
	if not frappe.db.exists("Quotation", name):
		return
	try:
		q = frappe.get_doc("Quotation", name)
		if q.docstatus == 1:
			q.flags.ignore_linked_doctypes = True
			q.cancel()
		frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
	except Exception:
		pass
