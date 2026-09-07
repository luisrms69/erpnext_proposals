"""Tests — issue #39 Fase 1: auto-creación de Project al pasar una Quotation a `Ganada`.

Cubre: toggle OFF no dispara; toggle ON encola (post-commit) reutilizando `create_project_from_quotation`;
idempotencia (no duplica Project); fallo de preflight deja la Quotation `Ganada` sin Project parcial;
save normal sin transición no dispara; transición a otro estado no dispara; resolución estricta por Company.

El disparo real usa `frappe.enqueue(..., enqueue_after_commit=True)`; en los tests de gating se intercepta
`frappe.enqueue` para verificar SI/NO se encola y con qué argumentos. La lógica del job se prueba llamando
`auto_create_project_on_won` directamente.
"""

import unittest

import frappe

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
from erpnext_proposals.erpnext_proposals.utils.project import auto_create_project_on_won

TEMPLATE = "_AW Template"
ITEM_OK = "_AW Item OK"  # scope con fase → Project válido
ITEM_NOPHASE = "_AW Item NoPhase"  # scope sin fase → preflight bloquea
CO_B = "_AW Co B"
CO_B_ABBR = "_AWB"
CUST = "_AW Cust"
JOB_PATH = "erpnext_proposals.erpnext_proposals.utils.project.auto_create_project_on_won"


class TestAutoProjectOnWon(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._q = []
		cls._p = []
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
		for code in (ITEM_OK, ITEM_NOPHASE):
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
		# ITEM_OK: 2 scope con fase; ITEM_NOPHASE: 1 scope SIN fase (visible → ejecutable → bloquea preflight).
		for i, (code, item, phase) in enumerate(
			[("_AW_S1", ITEM_OK, "DISC"), ("_AW_S2", ITEM_OK, "IMPL"), ("_AW_SNP", ITEM_NOPHASE, None)],
			start=1,
		):
			if not frappe.db.exists("Scope Item", code):
				d = {
					"doctype": "Scope Item",
					"code": code,
					"title": code,
					"sequence": i,
					"erpnext_item": item,
					"estimated_hours": 4,
					"enabled": 1,
					"visible_in_proposal": 1,
				}
				if phase:
					d["phase"] = phase
				frappe.get_doc(d).insert(ignore_permissions=True)
		cls.company_b = cls._ensure_company_b()

	@classmethod
	def _ensure_company_b(cls):
		if not frappe.db.exists("Company", CO_B):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": CO_B,
					"abbr": CO_B_ABBR,
					"default_currency": "MXN",
					"country": "Mexico",
				}
			).insert(ignore_permissions=True)
		return CO_B

	@classmethod
	def tearDownClass(cls):
		for p in cls._p:
			for t in frappe.get_all("Task", filters={"project": p}, pluck="name"):
				try:
					frappe.delete_doc("Task", t, force=True, ignore_permissions=True)
				except Exception:
					pass
			if frappe.db.exists("Project", p):
				try:
					frappe.delete_doc("Project", p, force=True, ignore_permissions=True)
				except Exception:
					pass
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
		for company in (cls.company, CO_B):
			name = frappe.db.get_value("Proposal Settings", {"company": company}, "name")
			if name:
				frappe.delete_doc("Proposal Settings", name, force=True, ignore_permissions=True)
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_AW_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		cleanup_test_phases(getattr(cls, "_phases", None))
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		super().tearDownClass()

	def tearDown(self):
		# Aislar el toggle por test.
		for company in (self.company, CO_B):
			name = frappe.db.get_value("Proposal Settings", {"company": company}, "name")
			if name:
				frappe.delete_doc("Proposal Settings", name, force=True, ignore_permissions=True)

	# ── Helpers ──────────────────────────────────────────────────────────────

	def _set_toggle(self, company, on):
		name = frappe.db.get_value("Proposal Settings", {"company": company}, "name")
		s = frappe.get_doc("Proposal Settings", name) if name else frappe.new_doc("Proposal Settings")
		s.company = company
		s.auto_create_project_on_won = 1 if on else 0
		s.flags.ignore_permissions = True
		s.save(ignore_permissions=True)

	def _quotation(self, company, cc, item=ITEM_OK, submit=True):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": CUST,
				"proposal_group": "AW-" + frappe.generate_hash(length=6),
				"company": company,
				"currency": "MXN",
				"selling_price_list": self.price_list,
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": cc,
				"proposal_title": "AW " + frappe.generate_hash(length=4),
				"items": [{"item_code": item, "item_name": item, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._q.append(doc.name)
		if submit:
			doc.reload()
			doc.flags.ignore_mandatory = True
			doc.flags.ignore_links = True
			doc.submit()
		return doc.name

	def _transition(self, quotation_name, new_state, from_state="Enviada al Cliente"):
		"""Fuerza el estado previo persistido y guarda con el nuevo estado → dispara el detector de
		transición en `validate`. Devuelve la lista de llamadas capturadas de `frappe.enqueue`."""
		frappe.db.set_value("Quotation", quotation_name, "workflow_state", from_state, update_modified=False)
		captured = []
		orig = frappe.enqueue

		def _spy(*a, **k):
			captured.append((a, k))

		frappe.enqueue = _spy
		try:
			doc = frappe.get_doc("Quotation", quotation_name)
			doc.workflow_state = new_state
			doc.save(ignore_permissions=True)
		finally:
			frappe.enqueue = orig
		return captured

	def _enqueued_job(self, captured, quotation_name):
		for a, k in captured:
			if a and a[0] == JOB_PATH and k.get("quotation_name") == quotation_name:
				return k
		return None

	def _track_project(self, quotation_name):
		p = frappe.db.get_value("Quotation", quotation_name, "proposal_project")
		if p:
			self.__class__._p.append(p)
		return p

	# ── Tests ────────────────────────────────────────────────────────────────

	def test_1_toggle_off_does_not_enqueue(self):
		self._set_toggle(self.company, on=False)
		q = self._quotation(self.company, self.cc)
		captured = self._transition(q, "Ganada")
		self.assertIsNone(self._enqueued_job(captured, q), "toggle OFF no debe encolar")

	def test_2_toggle_on_enqueues_after_commit(self):
		self._set_toggle(self.company, on=True)
		q = self._quotation(self.company, self.cc)
		captured = self._transition(q, "Ganada")
		job = self._enqueued_job(captured, q)
		self.assertIsNotNone(job, "toggle ON debe encolar el job")
		self.assertTrue(job.get("enqueue_after_commit"), "debe ser enqueue_after_commit=True (post-commit)")

	def test_2b_job_creates_project(self):
		self._set_toggle(self.company, on=True)
		q = self._quotation(self.company, self.cc)
		frappe.db.set_value("Quotation", q, "workflow_state", "Ganada", update_modified=False)
		auto_create_project_on_won(q)
		proj = self._track_project(q)
		self.assertTrue(proj and frappe.db.exists("Project", proj), "el job crea el Project")

	def test_3_existing_project_not_duplicated(self):
		self._set_toggle(self.company, on=True)
		q = self._quotation(self.company, self.cc)
		frappe.db.set_value("Quotation", q, "workflow_state", "Ganada", update_modified=False)
		auto_create_project_on_won(q)
		proj = self._track_project(q)
		n_projects = frappe.db.count("Project")
		auto_create_project_on_won(q)  # 2ª ejecución
		self.assertEqual(frappe.db.get_value("Quotation", q, "proposal_project"), proj)
		self.assertEqual(frappe.db.count("Project"), n_projects, "no duplica Project")

	def test_4_preflight_failure_keeps_ganada_no_partial_project(self):
		self._set_toggle(self.company, on=True)
		q = self._quotation(self.company, self.cc, item=ITEM_NOPHASE)  # scope sin fase
		frappe.db.set_value("Quotation", q, "workflow_state", "Ganada", update_modified=False)
		with self.assertRaises(frappe.ValidationError):
			auto_create_project_on_won(q)  # preflight bloquea (fila sin fase)
		self.assertFalse(
			frappe.db.get_value("Quotation", q, "proposal_project"), "no debe quedar Project parcial"
		)
		self.assertEqual(
			frappe.db.get_value("Quotation", q, "workflow_state"), "Ganada", "la transición permanece"
		)

	def test_5_normal_save_without_transition_does_not_enqueue(self):
		# Borrador (no submitted): un re-guardado sin cambio de estado (old == new == Borrador) no es
		# transición → no encola. (Un Borrador evita el guard de inmutabilidad de propuestas submitted.)
		self._set_toggle(self.company, on=True)
		q = self._quotation(self.company, self.cc, submit=False)
		captured = []
		orig = frappe.enqueue
		frappe.enqueue = lambda *a, **k: captured.append((a, k))
		try:
			doc = frappe.get_doc("Quotation", q)
			doc.save(ignore_permissions=True)
		finally:
			frappe.enqueue = orig
		self.assertIsNone(self._enqueued_job(captured, q), "un save sin transición no debe encolar")

	def test_6_transition_to_other_state_does_not_enqueue(self):
		self._set_toggle(self.company, on=True)
		q = self._quotation(self.company, self.cc)
		captured = self._transition(q, "Enviada al Cliente", from_state="Aprobada")
		self.assertIsNone(self._enqueued_job(captured, q), "transición a otro estado no debe encolar")

	def test_7_strict_per_company(self):
		# A: ON → encola; B: sin settings (o OFF) → no encola.
		self._set_toggle(self.company, on=True)
		self._set_toggle(CO_B, on=False)
		qa = self._quotation(self.company, self.cc)
		cc_b = get_test_cost_center(CO_B)
		qb = self._quotation(CO_B, cc_b)
		ca = self._transition(qa, "Ganada")
		cb = self._transition(qb, "Ganada")
		self.assertIsNotNone(self._enqueued_job(ca, qa), "Company A (ON) encola")
		self.assertIsNone(self._enqueued_job(cb, qb), "Company B (OFF) no encola")


if __name__ == "__main__":
	unittest.main()
