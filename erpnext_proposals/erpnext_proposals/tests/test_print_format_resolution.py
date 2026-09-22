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
	get_effective_commercial_print_format,
	is_eligible_print_format,
	resolve_commercial_print_format,
	sync_proposal_print_format_from_template,
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
		from erpnext_proposals.erpnext_proposals.tests.company import (
			get_test_company,
			get_test_cost_center,
		)

		cls.company = get_test_company()
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
		cls.cost_center = get_test_cost_center(cls.company)
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
		frappe.db.commit()  # nosemgrep — test isolation requires explicit commit

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
	def test_D_materialized_persists_and_immutable(self):
		# B8: el PF efectivo se MATERIALIZA en proposal_print_format (campo normal) e inmutable por
		# docstatus; el flujo nuevo NO escribe proposal_effective_print_format.
		q = self._submit_proposal(TPL_PF)
		try:
			self.assertEqual(q.proposal_print_format, ALT, "PF materializado = formato del template")
			self.assertFalse(
				(q.get("proposal_effective_print_format") or ""),
				"el flujo nuevo no escribe proposal_effective_print_format",
			)
			# cambiar el default del template → no debe afectar la propuesta formalizada
			frappe.db.set_value("Proposal Template", TPL_PF, "print_format", DEFAULT_COMMERCIAL_PRINT_FORMAT)
			fresh = frappe.get_doc("Quotation", q.name)
			self.assertEqual(fresh.proposal_print_format, ALT)
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
			self.assertFalse(v2.proposal_effective_print_format, "v2 no copia el congelado legacy")
			self.assertEqual(int(v2.docstatus), 0, "v2 en Borrador editable")
			# v1 intacta: el PF materializado sigue siendo ALT (flujo nuevo, en proposal_print_format)
			self.assertEqual(frappe.db.get_value("Quotation", q.name, "proposal_print_format"), ALT)
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

	# ── H — override INELEGIBLE (stale) se ignora y cae al template ───────────
	def test_H_eligibility_helper(self):
		self.assertTrue(is_eligible_print_format(ALT))
		self.assertFalse(is_eligible_print_format("_Test PF Disabled"))
		self.assertFalse(is_eligible_print_format("_Test PF Wrong Doctype"))
		self.assertFalse(is_eligible_print_format("_PF_inexistente_zzz"))
		self.assertFalse(is_eligible_print_format(None))

	def test_H_override_disabled_falls_to_template(self):
		doc = frappe._dict({"proposal_template": TPL_PF, "proposal_print_format": "_Test PF Disabled"})
		self.assertEqual(resolve_commercial_print_format(doc), ALT)

	def test_H_override_missing_falls_to_template(self):
		doc = frappe._dict({"proposal_template": TPL_PF, "proposal_print_format": "_PF_inexistente_zzz"})
		self.assertEqual(resolve_commercial_print_format(doc), ALT)

	def test_H_override_wrong_doctype_falls_to_template(self):
		doc = frappe._dict({"proposal_template": TPL_PF, "proposal_print_format": "_Test PF Wrong Doctype"})
		self.assertEqual(resolve_commercial_print_format(doc), ALT)

	def test_H_no_override_uses_template(self):
		doc = frappe._dict({"proposal_template": TPL_PF})
		self.assertEqual(resolve_commercial_print_format(doc), ALT)

	# ── I — sync corrige el campo stale sin pisar override manual válido ──────
	#   Se ejercita el flujo REAL (`doc.save()` → validate → sync): así `has_value_changed`
	#   tiene baseline (`_doc_before_save`). Llamar sync sobre un doc recién cargado sin baseline
	#   no reproduce el comportamiento de validate.
	def test_I_sync_fixes_stale_override(self):
		q = self._draft_proposal(TPL_PF)
		try:
			# override stale directamente en BD (bypass del sync), sin cambiar la plantilla
			frappe.db.set_value("Quotation", q.name, "proposal_print_format", "_Test PF Disabled")
			doc = frappe.get_doc("Quotation", q.name)
			self.assertEqual(doc.proposal_print_format, "_Test PF Disabled")
			doc.flags.ignore_mandatory = True
			doc.save(ignore_permissions=True)
			doc.reload()
			self.assertEqual(doc.proposal_print_format, ALT, "override inelegible → PF del template")
		finally:
			_cancel_delete(q.name)

	def test_I_sync_keeps_valid_manual_override(self):
		q = self._draft_proposal(TPL_PF)
		try:
			# override manual VÁLIDO distinto del PF de la plantilla; la plantilla no cambia
			frappe.db.set_value("Quotation", q.name, "proposal_print_format", DEFAULT_COMMERCIAL_PRINT_FORMAT)
			doc = frappe.get_doc("Quotation", q.name)
			doc.flags.ignore_mandatory = True
			doc.save(ignore_permissions=True)
			doc.reload()
			self.assertEqual(
				doc.proposal_print_format,
				DEFAULT_COMMERCIAL_PRINT_FORMAT,
				"no pisa un override manual válido mientras la plantilla no cambie",
			)
		finally:
			_cancel_delete(q.name)

	# ── J — freeze con override stale congela el PF VÁLIDO resuelto ───────────
	# ── K — Vista previa comercial y Descargar PDF Borrador → MISMO PF ────────
	def test_K_preview_and_download_same_pf(self):
		q = self._draft_proposal(TPL_PF)
		try:
			doc = frappe.get_doc("Quotation", q.name)
			expected = resolve_commercial_print_format(doc)
			self.assertEqual(get_effective_commercial_print_format(q.name), expected)
			self.assertEqual(expected, ALT)
		finally:
			_cancel_delete(q.name)

	# ── helper ────────────────────────────────────────────────────────────────
	def _submit_proposal(self, template):
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_price_list

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
				"selling_price_list": get_test_price_list(),
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

	def _draft_proposal(self, template):
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_price_list

		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": f"TEST-PFD-{frappe.generate_hash(length=6)}",
				"proposal_template": template,
				"proposal_title": "PF Draft Test",
				"proposal_cost_center": self.cost_center,
				"selling_price_list": get_test_price_list(),
				"items": [{"item_code": self.item, "qty": 1, "rate": 5000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
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
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_item_group

		ig = get_test_item_group()
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
