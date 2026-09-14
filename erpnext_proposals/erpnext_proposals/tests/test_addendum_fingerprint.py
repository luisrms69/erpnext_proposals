"""Tests — `get_addendum_delta_fingerprint` (Change Control v2, ADR-0019 §7.2; economía vía ADR-0020).

Huella canónica y ESTABLE del delta SEMÁNTICO CONGELADO de una addenda formal. Se cubre en dos niveles:

- **Canonicalización / sensibilidad** (mock ligero `frappe._dict` sobre `_addendum_delta_payload` +
  `_canonical_hash`): estabilidad ante orden físico, preservación de multiplicidad, indiferencia a campos
  técnicos, y sensibilidad a cada campo semántico (revenue/qty/esfuerzo/activity_type/designation/costing_rate/
  required/frozen_cost_rate/recurrencia/planificación).
- **Integración** (addendas reales congeladas): condiciones de entrada fail-closed (Borrador, no-addenda,
  snapshot incompleto), determinismo en llamadas repetidas y estabilidad entre versiones semánticamente iguales.
"""

import unittest

import frappe
from frappe.exceptions import ValidationError

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
from erpnext_proposals.erpnext_proposals.tests.phases import (
	cleanup_test_phases,
	ensure_test_phases,
)
from erpnext_proposals.erpnext_proposals.utils.addendum import (
	_addendum_delta_payload,
	_canonical_hash,
	get_addendum_delta_fingerprint,
)
from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import create_new_proposal_version

TEMPLATE = "_FP Template"
ITEM = "_FP Item"
REQ = "_FP Req"
CUST = "_FP Cust"


# ══ Nivel 1 — canonicalización / sensibilidad (mock, sin DB) ═══════════════════════════════════════


def _doc(items=None, scope=None, required=None, **technical):
	"""Doc mock: solo expone las colecciones que lee `_addendum_delta_payload`. `technical` agrega campos
	técnicos (name, proposal_version, ...) que la huella DEBE ignorar."""
	return frappe._dict(
		items=[frappe._dict(x) for x in (items or [])],
		quotation_scope_items=[frappe._dict(x) for x in (scope or [])],
		required_items=[frappe._dict(x) for x in (required or [])],
		**technical,
	)


def _fp(doc) -> str:
	return _canonical_hash(_addendum_delta_payload(doc))


def _sold(**over):
	base = {
		"item_code": ITEM,
		"uom": "Nos",
		"qty": 1,
		"rate": 1000,
		"net_amount": 1000,
		"proposal_economic_behavior": "one_time",
		"proposal_billing_interval": "",
		"proposal_billing_interval_count": 0,
	}
	base.update(over)
	return base


def _scope(**over):
	base = {
		"code": "S1",
		"item_code": ITEM,
		"phase": "DISC",
		"include_in_proposal": 1,
		"is_internal_cost_task": 0,
		"estimated_hours": 4,
		"activity_type": "AT",
		"designation": "DES",
		"costing_rate": 500,
		"planned_start_offset_days": 0,
		"planned_duration_days": 2,
		"is_milestone": 0,
		"dependency_scope_item_codes": "[]",
	}
	base.update(over)
	return base


def _req(**over):
	base = {
		"item": REQ,
		"qty": 1,
		"uom": "Nos",
		"frozen_cost_rate": 100,
		"economic_behavior": "one_time",
		"billing_interval": "",
		"billing_interval_count": 0,
	}
	base.update(over)
	return base


class TestFingerprintCanonicalization(unittest.TestCase):
	def _base(self):
		return _doc(items=[_sold()], scope=[_scope()], required=[_req()])

	def test_01_deterministic_repeated(self):
		self.assertEqual(_fp(self._base()), _fp(self._base()))

	def test_03_revenue_rate_changes_hash(self):
		self.assertNotEqual(_fp(self._base()), _fp(_doc(items=[_sold(rate=2000, net_amount=2000)])))

	def test_04_qty_changes_hash(self):
		self.assertNotEqual(
			_fp(self._base()), _fp(_doc(items=[_sold(qty=2)], scope=[_scope()], required=[_req()]))
		)

	def test_05_estimated_hours_changes_hash(self):
		a = self._base()
		b = _doc(items=[_sold()], scope=[_scope(estimated_hours=8)], required=[_req()])
		self.assertNotEqual(_fp(a), _fp(b))

	def test_06_activity_type_changes_hash(self):
		b = _doc(items=[_sold()], scope=[_scope(activity_type="OTHER")], required=[_req()])
		self.assertNotEqual(_fp(self._base()), _fp(b))

	def test_07_designation_changes_hash(self):
		b = _doc(items=[_sold()], scope=[_scope(designation="OTHER")], required=[_req()])
		self.assertNotEqual(_fp(self._base()), _fp(b))

	def test_08_costing_rate_changes_hash(self):
		b = _doc(items=[_sold()], scope=[_scope(costing_rate=999)], required=[_req()])
		self.assertNotEqual(_fp(self._base()), _fp(b))

	def test_08a_include_in_proposal_changes_hash(self):
		"""Materialización: cambiar `include_in_proposal` (ejecutabilidad) cambia la huella."""
		b = _doc(items=[_sold()], scope=[_scope(include_in_proposal=0)], required=[_req()])
		self.assertNotEqual(_fp(self._base()), _fp(b))

	def test_08b_is_internal_cost_task_changes_hash(self):
		"""Materialización: cambiar `is_internal_cost_task` (ejecutabilidad interna) cambia la huella."""
		b = _doc(items=[_sold()], scope=[_scope(is_internal_cost_task=1)], required=[_req()])
		self.assertNotEqual(_fp(self._base()), _fp(b))

	def test_08c_phase_changes_hash(self):
		"""Materialización: cambiar `phase` (Task-fase donde se materializa) cambia la huella."""
		b = _doc(items=[_sold()], scope=[_scope(phase="IMPL")], required=[_req()])
		self.assertNotEqual(_fp(self._base()), _fp(b))

	def test_08d_item_code_changes_hash(self):
		"""Materialización: cambiar `item_code` (atribución de la fila al Item vendido, y subject de la Task)
		cambia la huella."""
		b = _doc(items=[_sold()], scope=[_scope(item_code="_FP Item Other")], required=[_req()])
		self.assertNotEqual(_fp(self._base()), _fp(b))

	def test_09_required_item_changes_hash(self):
		b = _doc(items=[_sold()], scope=[_scope()], required=[_req(item="_FP Req Other")])
		self.assertNotEqual(_fp(self._base()), _fp(b))

	def test_10_frozen_cost_rate_changes_hash(self):
		b = _doc(items=[_sold()], scope=[_scope()], required=[_req(frozen_cost_rate=250)])
		self.assertNotEqual(_fp(self._base()), _fp(b))

	def test_11a_sold_economic_behavior_changes_hash(self):
		"""Punto D: un cambio de recurrencia en la línea vendida NO debe producir la misma huella."""
		b = _doc(
			items=[
				_sold(
					proposal_economic_behavior="recurring",
					proposal_billing_interval="Month",
					proposal_billing_interval_count=1,
				)
			],
			scope=[_scope()],
			required=[_req()],
		)
		self.assertNotEqual(_fp(self._base()), _fp(b))

	def test_11b_required_economic_behavior_changes_hash(self):
		b = _doc(
			items=[_sold()],
			scope=[_scope()],
			required=[
				_req(economic_behavior="recurring", billing_interval="Month", billing_interval_count=3)
			],
		)
		self.assertNotEqual(_fp(self._base()), _fp(b))

	def test_12a_planning_offset_changes_hash(self):
		b = _doc(items=[_sold()], scope=[_scope(planned_start_offset_days=5)], required=[_req()])
		self.assertNotEqual(_fp(self._base()), _fp(b))

	def test_12b_planning_duration_changes_hash(self):
		b = _doc(items=[_sold()], scope=[_scope(planned_duration_days=10)], required=[_req()])
		self.assertNotEqual(_fp(self._base()), _fp(b))

	def test_12c_milestone_changes_hash(self):
		b = _doc(items=[_sold()], scope=[_scope(is_milestone=1)], required=[_req()])
		self.assertNotEqual(_fp(self._base()), _fp(b))

	def test_12d_dependencies_change_hash(self):
		b = _doc(items=[_sold()], scope=[_scope(dependency_scope_item_codes='["S0"]')], required=[_req()])
		self.assertNotEqual(_fp(self._base()), _fp(b))

	def test_13_technical_fields_ignored(self):
		"""Cambiar solo name/proposal_version/previous_proposal/timestamps/proposal_project NO cambia la huella."""
		a = self._base()
		b = _doc(
			items=[_sold()],
			scope=[_scope()],
			required=[_req()],
			name="QTN-XYZ",
			proposal_version=7,
			previous_proposal="QTN-OLD",
			superseded_by_proposal="QTN-NEW",
			proposal_project="PROJ-1",
			creation="2020-01-01",
			modified="2020-01-02",
			owner="someone@x.com",
		)
		self.assertEqual(_fp(a), _fp(b))

	def test_14_physical_order_irrelevant(self):
		s1, s2 = _scope(code="A"), _scope(code="B")
		a = _doc(scope=[s1, s2])
		b = _doc(scope=[s2, s1])
		self.assertEqual(_fp(a), _fp(b))

	def test_15_multiplicity_preserved(self):
		"""Dos filas iguales NO colapsan a una sola."""
		one = _doc(items=[_sold()])
		two = _doc(items=[_sold(), _sold()])
		self.assertNotEqual(_fp(one), _fp(two))

	def test_15b_dependency_serialization_order_irrelevant(self):
		"""`dependency_scope_item_codes` se canonicaliza por conjunto: distinto orden serializado = misma huella."""
		a = _doc(scope=[_scope(dependency_scope_item_codes='["A","B"]')])
		b = _doc(scope=[_scope(dependency_scope_item_codes='["B","A"]')])
		self.assertEqual(_fp(a), _fp(b))

	def test_15c_dependency_duplicates_set_semantics(self):
		"""Las dependencias son un CONJUNTO: `["A","A"]` canonicaliza IGUAL que `["A"]` (multiplicidad
		sin significado — así las consume `_resolve_native_dependencies`)."""
		a = _doc(scope=[_scope(dependency_scope_item_codes='["A","A"]')])
		b = _doc(scope=[_scope(dependency_scope_item_codes='["A"]')])
		self.assertEqual(_fp(a), _fp(b))

	def test_dep_invalid_json_fail_closed(self):
		"""JSON inválido presente → fail-closed (no se degrada a []), para no ocultar dependencia corrupta."""
		with self.assertRaises(ValidationError):
			_fp(_doc(scope=[_scope(dependency_scope_item_codes="{no-es-json")]))

	def test_dep_not_list_fail_closed(self):
		"""JSON válido pero que NO es una lista → fail-closed."""
		with self.assertRaises(ValidationError):
			_fp(_doc(scope=[_scope(dependency_scope_item_codes='{"a": 1}')]))

	def test_dep_empty_forms_ok(self):
		"""Vacío legítimo (None / "" / "[]") canonicaliza como [] sin lanzar; los tres son equivalentes."""
		h_none = _fp(_doc(scope=[_scope(dependency_scope_item_codes=None)]))
		h_empty = _fp(_doc(scope=[_scope(dependency_scope_item_codes="")]))
		h_brackets = _fp(_doc(scope=[_scope(dependency_scope_item_codes="[]")]))
		self.assertEqual(h_none, h_empty)
		self.assertEqual(h_empty, h_brackets)


# ══ Nivel 2 — integración con addendas reales congeladas ════════════════════════════════════════════


class TestFingerprintIntegration(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._q = []
		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company on test site.")
		cls._phases = ensure_test_phases()  # DISC(10), IMPL(20), GOLIVE(30)
		cls._fy = ensure_current_fiscal_year()
		cls.price_list = get_test_price_list()
		cls.cc = get_test_cost_center(cls.company)
		ig = get_test_item_group()
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {}, "name")
		if not cg:
			raise unittest.SkipTest("No Customer Group on test site.")
		if not frappe.db.exists("Customer", CUST):
			frappe.get_doc(
				{"doctype": "Customer", "customer_name": CUST, "customer_group": cg, "territory": terr}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		for code in (ITEM, REQ):
			if not frappe.db.exists("Item", code):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_name": code,
						"item_group": ig,
						"stock_uom": "Nos",
						"is_stock_item": 0,
						"is_sales_item": 1,
					}
				).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "t"}
			).insert(ignore_permissions=True)
		for i, (code, phase) in enumerate([("_FP_S1", "DISC"), ("_FP_S2", "IMPL")], start=1):
			if not frappe.db.exists("Scope Item", code):
				frappe.get_doc(
					{
						"doctype": "Scope Item",
						"code": code,
						"title": code,
						"sequence": i,
						"erpnext_item": ITEM,
						"phase": phase,
						"estimated_hours": 4,
						"enabled": 1,
						"visible_in_proposal": 1,
					}
				).insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		for n in cls._q:
			if frappe.db.exists("Quotation", n):
				try:
					d = frappe.get_doc("Quotation", n)
					if d.docstatus == 1:
						d.flags.ignore_linked_doctypes = True
						d.cancel()
					frappe.delete_doc("Quotation", n, force=True, ignore_permissions=True)
				except Exception:
					pass
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_FP_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		cleanup_test_phases(getattr(cls, "_phases", None))
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		super().tearDownClass()

	def _quotation(self, *, group, addendum=True, submit=True, required=None, rate=1000):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": CUST,
				"proposal_group": group,
				"company": self.company,
				"currency": "MXN",
				"selling_price_list": self.price_list,
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cc,
				"proposal_title": "FP " + frappe.generate_hash(length=4),
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": rate, "uom": "Nos"}],
				"required_items": [{"item": it, "qty": q, "uom": "Nos"} for (it, q) in (required or [])],
			}
		)
		if addendum:
			doc.flags.from_addendum_creation = True
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._q.append(doc.name)
		if submit:
			doc.reload()
			doc.flags.ignore_mandatory = True
			doc.flags.ignore_links = True
			doc.submit()  # before_submit → freeze + assert_economic_snapshot_complete
		return frappe.get_doc("Quotation", doc.name)

	def _grp(self):
		return f"FP-{frappe.generate_hash(length=6)}-ADD-01"

	# ── #1 determinismo en llamadas repetidas ────────────────────────────────
	def test_int_01_repeated_calls_same(self):
		a = self._quotation(group=self._grp(), required=[(REQ, 1)])
		self.assertEqual(get_addendum_delta_fingerprint(a.name), get_addendum_delta_fingerprint(a.name))

	# ── #2 nueva versión con el mismo delta → misma huella ───────────────────
	def test_int_02_new_version_same_delta_same_fp(self):
		grp = self._grp()
		v1 = self._quotation(group=grp, required=[(REQ, 1)])
		fp1 = get_addendum_delta_fingerprint(v1.name)
		# Rechazar para poder versionar; la v2 copia el mismo delta y re-congela iguales valores.
		frappe.db.set_value("Quotation", v1.name, "workflow_state", "Rechazada", update_modified=False)
		v2_name = create_new_proposal_version(v1.name, reason="Regresión fingerprint estable")
		self.__class__._q.append(v2_name)
		v2 = frappe.get_doc("Quotation", v2_name)
		v2.flags.ignore_mandatory = True
		v2.flags.ignore_links = True
		v2.submit()
		self.assertEqual(fp1, get_addendum_delta_fingerprint(v2_name), "misma semántica → misma huella")

	# ── #16 Borrador → fail-closed ───────────────────────────────────────────
	def test_int_16_draft_rejected(self):
		a = self._quotation(group=self._grp(), submit=False)
		self.assertEqual(a.docstatus, 0)
		with self.assertRaises(ValidationError):
			get_addendum_delta_fingerprint(a.name)

	# ── #17 Quotation normal (no addenda) → fail-closed ──────────────────────
	def test_int_17_non_addendum_rejected(self):
		normal = self._quotation(group=f"FP-NORMAL-{frappe.generate_hash(length=6)}", addendum=False)
		with self.assertRaises(ValidationError):
			get_addendum_delta_fingerprint(normal.name)

	# ── #18 snapshot económico incompleto → fail-closed ──────────────────────
	def test_int_18_incomplete_snapshot_rejected(self):
		a = self._quotation(group=self._grp())
		# Corromper el snapshot congelado de una línea vendida (bypass privilegiado, no ruta de usuario).
		item_row = a.items[0].name
		frappe.db.set_value(
			"Quotation Item", item_row, "proposal_economic_behavior", "", update_modified=False
		)
		with self.assertRaises(ValidationError):
			get_addendum_delta_fingerprint(a.name)


if __name__ == "__main__":
	unittest.main()
