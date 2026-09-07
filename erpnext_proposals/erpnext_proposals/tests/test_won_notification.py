"""Tests — issue #39 Fase 1 (2ª acción): correo de notificación al pasar una Quotation a `Ganada`.

Cubre: toggle OFF no encola; ON + destino encola (post-commit, dedup); estricto por Company; Email Template
configurada → subject/body renderizados; sin plantilla → fallback del app; destino ausente con toggle ON no
envía; save sin transición no encola; transición != Ganada no encola; independencia respecto de auto-Project.

Gating por transición: se intercepta `frappe.enqueue`. La lógica del job (render/fallback/envío) se prueba
llamando `send_won_notification_email` directamente e interceptando `frappe.sendmail`.
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
from erpnext_proposals.erpnext_proposals.utils.won_notification import send_won_notification_email

TEMPLATE = "_WN Template"
ITEM = "_WN Item"
CO_B = "_WN Co B"
CO_B_ABBR = "_WNB"
CUST = "_WN Cust"
EMAIL = "ops@example.com"
ET_NAME = "_WN Email Template"
WON_JOB = "erpnext_proposals.erpnext_proposals.utils.won_notification.send_won_notification_email"
PROJ_JOB = "erpnext_proposals.erpnext_proposals.utils.project.auto_create_project_on_won"


class TestWonNotification(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._q = []
		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company on test site.")
		cls._phases = ensure_test_phases()
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
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": ITEM,
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
		if not frappe.db.exists("Scope Item", "_WN_S1"):
			frappe.get_doc(
				{
					"doctype": "Scope Item",
					"code": "_WN_S1",
					"title": "_WN_S1",
					"sequence": 1,
					"erpnext_item": ITEM,
					"phase": "DISC",
					"estimated_hours": 4,
					"enabled": 1,
					"visible_in_proposal": 1,
				}
			).insert(ignore_permissions=True)
		# Email Template nativa: subject/body con contexto {{ doc }}.
		if not frappe.db.exists("Email Template", ET_NAME):
			frappe.get_doc(
				{
					"doctype": "Email Template",
					"name": ET_NAME,
					"subject": "Ganada: {{ name }}",
					"response": "Cliente {{ party_name }} ganó la propuesta.",
					"use_html": 0,
				}
			).insert(ignore_permissions=True)
		cls.company_b = cls._ensure_company_b()
		cls.cc_b = get_test_cost_center(CO_B)

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
		if frappe.db.exists("Email Template", ET_NAME):
			frappe.delete_doc("Email Template", ET_NAME, force=True, ignore_permissions=True)
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_WN_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		cleanup_test_phases(getattr(cls, "_phases", None))
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		super().tearDownClass()

	def tearDown(self):
		for company in (self.company, CO_B):
			name = frappe.db.get_value("Proposal Settings", {"company": company}, "name")
			if name:
				frappe.delete_doc("Proposal Settings", name, force=True, ignore_permissions=True)

	# ── Helpers ──────────────────────────────────────────────────────────────

	def _settings(self, company, project_on=False, email_on=False, email=None, template=None):
		name = frappe.db.get_value("Proposal Settings", {"company": company}, "name")
		s = frappe.get_doc("Proposal Settings", name) if name else frappe.new_doc("Proposal Settings")
		s.company = company
		s.auto_create_project_on_won = 1 if project_on else 0
		s.send_won_notification_email = 1 if email_on else 0
		s.won_notification_email = email
		s.won_notification_email_template = template
		s.flags.ignore_permissions = True
		s.save(ignore_permissions=True)

	def _quotation(self, company, cc, submit=True):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": CUST,
				"proposal_group": "WN-" + frappe.generate_hash(length=6),
				"company": company,
				"currency": "MXN",
				"selling_price_list": self.price_list,
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": cc,
				"proposal_title": "WN " + frappe.generate_hash(length=4),
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}],
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
		frappe.db.set_value("Quotation", quotation_name, "workflow_state", from_state, update_modified=False)
		captured = []
		orig = frappe.enqueue
		frappe.enqueue = lambda *a, **k: captured.append((a, k))
		try:
			doc = frappe.get_doc("Quotation", quotation_name)
			doc.workflow_state = new_state
			doc.save(ignore_permissions=True)
		finally:
			frappe.enqueue = orig
		return captured

	def _has_job(self, captured, path, quotation_name):
		for a, k in captured:
			if a and a[0] == path and k.get("quotation_name") == quotation_name:
				return k
		return None

	def _run_job_capturing_email(self, quotation_name):
		sent = {}
		orig = frappe.sendmail
		frappe.sendmail = lambda **k: sent.update(k)
		try:
			send_won_notification_email(quotation_name)
		finally:
			frappe.sendmail = orig
		return sent

	def _make_ganada(self, company, cc):
		q = self._quotation(company, cc)
		frappe.db.set_value("Quotation", q, "workflow_state", "Ganada", update_modified=False)
		return q

	# ── Tests ────────────────────────────────────────────────────────────────

	def test_1_toggle_off_does_not_enqueue(self):
		self._settings(self.company, email_on=False)
		q = self._quotation(self.company, self.cc)
		captured = self._transition(q, "Ganada")
		self.assertIsNone(self._has_job(captured, WON_JOB, q), "toggle OFF no encola correo")

	def test_2_toggle_on_with_email_enqueues(self):
		self._settings(self.company, email_on=True, email=EMAIL)
		q = self._quotation(self.company, self.cc)
		captured = self._transition(q, "Ganada")
		job = self._has_job(captured, WON_JOB, q)
		self.assertIsNotNone(job, "toggle ON + destino encola el correo")
		self.assertTrue(job.get("enqueue_after_commit"), "post-commit")
		self.assertTrue(job.get("deduplicate"), "dedup nativo")
		self.assertEqual(job.get("job_id"), f"won_notification::{q}", "job_id estable para dedup")

	def test_3_strict_per_company(self):
		self._settings(self.company, email_on=True, email=EMAIL)
		self._settings(CO_B, email_on=False)
		qa = self._quotation(self.company, self.cc)
		qb = self._quotation(CO_B, self.cc_b)
		self.assertIsNotNone(self._has_job(self._transition(qa, "Ganada"), WON_JOB, qa), "A (ON) encola")
		self.assertIsNone(self._has_job(self._transition(qb, "Ganada"), WON_JOB, qb), "B (OFF) no encola")

	def test_4_email_template_rendered(self):
		self._settings(self.company, email_on=True, email=EMAIL, template=ET_NAME)
		q = self._make_ganada(self.company, self.cc)
		sent = self._run_job_capturing_email(q)
		self.assertEqual(sent.get("subject"), f"Ganada: {q}", "subject renderizado desde la plantilla")
		self.assertIn(CUST, sent.get("message", ""), "body renderizado con contexto de la Quotation")
		self.assertEqual(sent.get("recipients"), [EMAIL])
		self.assertEqual(sent.get("reference_doctype"), "Quotation")
		self.assertEqual(sent.get("reference_name"), q)

	def test_5_fallback_without_template(self):
		self._settings(self.company, email_on=True, email=EMAIL)  # sin plantilla
		q = self._make_ganada(self.company, self.cc)
		title = frappe.db.get_value("Quotation", q, "proposal_title")
		sent = self._run_job_capturing_email(q)
		self.assertEqual(sent.get("subject"), f"Propuesta ganada: {title}", "fallback de subject")
		self.assertIn("ha sido marcada como Ganada", sent.get("message", ""), "fallback de body")
		self.assertIn(q, sent.get("message", ""), "incluye enlace/nombre de la Quotation")

	def test_6_email_missing_with_toggle_on_does_not_send(self):
		# El DocType exige el correo (mandatory_depends_on); forzamos el estado inválido por db.set_value.
		self._settings(self.company, email_on=False)
		name = frappe.db.get_value("Proposal Settings", {"company": self.company}, "name")
		frappe.db.set_value(
			"Proposal Settings", name, "send_won_notification_email", 1, update_modified=False
		)
		q = self._make_ganada(self.company, self.cc)
		sent = self._run_job_capturing_email(q)
		self.assertEqual(sent, {}, "config inválida (sin destino) no envía")
		# Y el gate del enqueue tampoco encola (transición válida a Ganada).
		self.assertIsNone(
			self._has_job(self._transition(q, "Ganada", from_state="Enviada al Cliente"), WON_JOB, q)
		)

	def test_7_normal_save_without_transition_does_not_enqueue(self):
		# Borrador (no submitted): re-guardado sin cambio de estado no es transición → no encola.
		self._settings(self.company, email_on=True, email=EMAIL)
		q = self._quotation(self.company, self.cc, submit=False)
		captured = []
		orig = frappe.enqueue
		frappe.enqueue = lambda *a, **k: captured.append((a, k))
		try:
			doc = frappe.get_doc("Quotation", q)
			doc.save(ignore_permissions=True)  # sin cambiar el estado
		finally:
			frappe.enqueue = orig
		self.assertIsNone(self._has_job(captured, WON_JOB, q), "save sin transición no encola")

	def test_8_transition_to_other_state_does_not_enqueue(self):
		self._settings(self.company, email_on=True, email=EMAIL)
		q = self._quotation(self.company, self.cc)
		captured = self._transition(q, "Enviada al Cliente", from_state="Aprobada")
		self.assertIsNone(self._has_job(captured, WON_JOB, q), "transición != Ganada no encola")

	def test_9_independent_from_auto_project(self):
		# correo ON / project OFF → solo correo.
		self._settings(self.company, project_on=False, email_on=True, email=EMAIL)
		q1 = self._quotation(self.company, self.cc)
		c1 = self._transition(q1, "Ganada")
		self.assertIsNotNone(self._has_job(c1, WON_JOB, q1), "correo encolado")
		self.assertIsNone(self._has_job(c1, PROJ_JOB, q1), "project NO encolado")
		# project ON / correo OFF → solo project.
		self._settings(self.company, project_on=True, email_on=False)
		q2 = self._quotation(self.company, self.cc)
		c2 = self._transition(q2, "Ganada")
		self.assertIsNotNone(self._has_job(c2, PROJ_JOB, q2), "project encolado")
		self.assertIsNone(self._has_job(c2, WON_JOB, q2), "correo NO encolado")


if __name__ == "__main__":
	unittest.main()
