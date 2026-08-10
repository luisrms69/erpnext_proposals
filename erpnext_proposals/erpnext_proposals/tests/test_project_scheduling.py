"""Programación de Tasks al crear el Proyecto: fechas por offset o propagación por dependencias,
offsets negativos, hitos, dependencias nativas (Task.depends_on) en segundo paso idempotente,
omisión de predecesores no contratados, roll-up de fechas de fase, reintento tras ejecución
parcial y Scope Items sin planeación PMO (sin fechas inventadas).

Datos ficticios; nunca contenido de cliente.
"""

import unittest

import frappe
from frappe.utils import add_days, getdate

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils.project import create_project_from_quotation

TEMPLATE = "_Test SCHED Template"
ITEM = "_Test SCHED Item"
ITEM_OPT = "_Test SCHED Item Opt"
PHASES = (("SCHEDP1", "Fase 1", 10), ("SCHEDP2", "Fase 2", 20))


class TestProjectScheduling(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_company

		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company found on test site.")
		cls._quotations = []
		cls._projects = []
		cls._created_fy = ensure_current_fiscal_year()
		cls._created_phases = []
		for code, name, seq in PHASES:
			if not frappe.db.exists("Proposal Phase", code):
				frappe.get_doc(
					{
						"doctype": "Proposal Phase",
						"phase_code": code,
						"phase_name": name,
						"sequence": seq,
						"enabled": 1,
					}
				).insert(ignore_permissions=True)
				cls._created_phases.append(code)
		cls._setup()

	@classmethod
	def tearDownClass(cls):
		for pj in cls._projects:
			for t in frappe.get_all("Task", filters={"project": pj}, pluck="name"):
				try:
					frappe.delete_doc("Task", t, force=True, ignore_permissions=True)
				except Exception:
					pass
			if frappe.db.exists("Project", pj):
				try:
					frappe.delete_doc("Project", pj, force=True, ignore_permissions=True)
				except Exception:
					pass
		for name in cls._quotations:
			if frappe.db.exists("Quotation", name):
				try:
					doc = frappe.get_doc("Quotation", name)
					if doc.docstatus == 1:
						doc.flags.ignore_linked_doctypes = True
						doc.cancel()
					frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
				except Exception:
					pass
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_SCHED_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		for code in getattr(cls, "_created_phases", []):
			if frappe.db.exists("Proposal Phase", code):
				frappe.delete_doc("Proposal Phase", code, force=True, ignore_permissions=True)
		cleanup_fiscal_year(getattr(cls, "_created_fy", None))
		super().tearDownClass()

	@classmethod
	def _setup(cls):
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_item_group

		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {}, "name")
		if not frappe.db.exists("Customer", "_Test SCHED Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test SCHED Customer",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test SCHED Customer"
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		ig = get_test_item_group()
		for code in (ITEM, ITEM_OPT):
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
		cls.cost_center = frappe.db.get_value("Cost Center", {"is_group": 0}, "name")

		# offset es Data nullable: "0" = inicio explícito; None/"" = sin offset; "-5"/"10" = ± días.
		# Predecesor opcional (en ITEM_OPT, NO contratado en las Quotations de scheduling).
		cls._scope("_SCHED_OPT", ITEM_OPT, "SCHEDP1", seq=5, offset="0", duration=2, milestone=0, deps=None)
		# Scope Items contratados en ITEM:
		#  S1: offset explícito "0", dur 2 (fase 1) → inicio en Project.expected_start_date
		cls._scope("_SCHED_S1", ITEM, "SCHEDP1", seq=10, offset="0", duration=2, milestone=0, deps=None)
		#  S2: SIN offset (None), depende de S1, dur 3 → inicio = fin(S1)+1
		cls._scope(
			"_SCHED_S2", ITEM, "SCHEDP1", seq=20, offset=None, duration=3, milestone=0, deps=["_SCHED_S1"]
		)
		#  S3: offset negativo "-5", dur 1
		cls._scope("_SCHED_S3", ITEM, "SCHEDP1", seq=30, offset="-5", duration=1, milestone=0, deps=None)
		#  S4: hito, offset "10" (fase 2)
		cls._scope("_SCHED_S4", ITEM, "SCHEDP2", seq=40, offset="10", duration=99, milestone=1, deps=None)
		#  S5: sin offset y sin predecesora fechada → NO fechable (distinto de "0")
		cls._scope("_SCHED_S5", ITEM, "SCHEDP2", seq=50, offset=None, duration=None, milestone=0, deps=None)
		#  S6: depende de un Scope Item NO contratado (_SCHED_OPT) → dependencia omitida; sin fecha
		cls._scope(
			"_SCHED_S6", ITEM, "SCHEDP2", seq=60, offset=None, duration=2, milestone=0, deps=["_SCHED_OPT"]
		)
		#  S7: SIN offset, depende de S2 → cadena de varias dependencias S1→S2→S7 (inicio = fin(S2)+1)
		cls._scope(
			"_SCHED_S7", ITEM, "SCHEDP1", seq=25, offset=None, duration=2, milestone=0, deps=["_SCHED_S2"]
		)

	@classmethod
	def _scope(cls, code, item, phase, seq, offset, duration, milestone, deps):
		if frappe.db.exists("Scope Item", code):
			return
		doc = frappe.get_doc(
			{
				"doctype": "Scope Item",
				"code": code,
				"title": code,
				"sequence": seq,
				"erpnext_item": item,
				"phase": phase,
				"enabled": 1,
				"visible_in_proposal": 1,
				"estimated_hours": 4,
				"planned_start_offset_days": offset,
				"planned_duration_days": duration,
				"is_milestone": milestone,
			}
		)
		for d in deps or []:
			doc.append("depends_on_scope_items", {"depends_on": d})
		doc.insert(ignore_permissions=True)

	def _make_ganada(self, item_codes):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "SCHED-" + frappe.generate_hash(length=6),
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cost_center,
				"proposal_title": "SCHED " + frappe.generate_hash(length=4),
				"items": [
					{"item_code": c, "item_name": c, "qty": 1, "rate": 1000, "uom": "Nos"} for c in item_codes
				],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._quotations.append(doc.name)
		doc.reload()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		frappe.db.set_value("Quotation", doc.name, "workflow_state", "Ganada", update_modified=False)
		return frappe.get_doc("Quotation", doc.name)

	def _task_for(self, project, scope_code):
		"""Task hija cuya fila de scope tiene ese code."""
		rows = frappe.get_all(
			"Task",
			filters={"project": project, "is_group": 0},
			fields=["name", "exp_start_date", "exp_end_date", "is_milestone", "source_quotation_scope_item"],
		)
		for t in rows:
			code = frappe.db.get_value("Quotation Scope Item", t.source_quotation_scope_item, "code")
			if code == scope_code:
				return t
		return None

	# ── Snapshot congelado en la Quotation ──

	def test_planning_frozen_into_quotation_scope(self):
		q = self._make_ganada([ITEM])
		row = next(r for r in q.quotation_scope_items if r.code == "_SCHED_S2")
		# Sin offset → vacío/NULL congelado (distinto de "0").
		self.assertIn(row.planned_start_offset_days, (None, ""))
		self.assertEqual(row.planned_duration_days, 3)
		self.assertIn("_SCHED_S1", row.dependency_scope_item_codes)
		s3 = next(r for r in q.quotation_scope_items if r.code == "_SCHED_S3")
		self.assertEqual(s3.planned_start_offset_days, "-5")  # Data (texto), no int
		s4 = next(r for r in q.quotation_scope_items if r.code == "_SCHED_S4")
		self.assertEqual(int(s4.is_milestone), 1)

	# ── Fechas / duración / offset / hito / propagación ──

	def test_scheduling_dates(self):
		q = self._make_ganada([ITEM])
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])
		start = getdate(frappe.utils.today())

		s1 = self._task_for(res["project"], "_SCHED_S1")
		self.assertEqual(getdate(s1.exp_start_date), start)
		self.assertEqual(getdate(s1.exp_end_date), add_days(start, 1))  # dur 2 → start + 1

		# S2 sin offset: inicio = fin(S1)+1 = start+2; fin = start+2 + (3-1) = start+4
		s2 = self._task_for(res["project"], "_SCHED_S2")
		self.assertEqual(getdate(s2.exp_start_date), add_days(start, 2))
		self.assertEqual(getdate(s2.exp_end_date), add_days(start, 4))

		# S3 offset negativo -5, dur 1 → una sola fecha
		s3 = self._task_for(res["project"], "_SCHED_S3")
		self.assertEqual(getdate(s3.exp_start_date), add_days(start, -5))
		self.assertEqual(getdate(s3.exp_end_date), add_days(start, -5))

		# S4 hito: exp_end == exp_start (offset 10), ignora la 'duración'
		s4 = self._task_for(res["project"], "_SCHED_S4")
		self.assertEqual(getdate(s4.exp_start_date), add_days(start, 10))
		self.assertEqual(getdate(s4.exp_end_date), add_days(start, 10))
		self.assertEqual(int(s4.is_milestone), 1)

	def test_undatable_reported_and_no_dates(self):
		q = self._make_ganada([ITEM])
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])
		# S5 (sin offset, sin predecesora) y S6 (dep a no contratado) quedan sin fecha.
		undatable_scopes = {u["subject"] for u in res["undatable_tasks"]}
		s5 = self._task_for(res["project"], "_SCHED_S5")
		s6 = self._task_for(res["project"], "_SCHED_S6")
		self.assertIsNone(s5.exp_start_date)
		self.assertIsNone(s6.exp_start_date)
		# El scope name (== code) de S5/S6 debe estar reportado como no fechable.
		self.assertIn("_SCHED_S5", undatable_scopes)
		self.assertIn("_SCHED_S6", undatable_scopes)

	# ── Dependencias nativas (segundo paso) ──

	def test_native_dependency_created_and_idempotent(self):
		q = self._make_ganada([ITEM])
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])
		s1 = self._task_for(res["project"], "_SCHED_S1")
		s2 = self._task_for(res["project"], "_SCHED_S2")
		deps = frappe.get_all("Task Depends On", filters={"parent": s2.name}, pluck="task")
		self.assertIn(s1.name, deps, "S2 debe depender de S1 en Task.depends_on nativo")
		self.assertGreaterEqual(res["dependencies_created"], 1)
		# Reejecutar no duplica.
		res2 = create_project_from_quotation(q.name)
		self.assertEqual(res2["dependencies_created"], 0)
		deps2 = frappe.get_all("Task Depends On", filters={"parent": s2.name}, pluck="task")
		self.assertEqual(len(deps), len(deps2))

	def test_dependency_to_uncontracted_is_skipped(self):
		q = self._make_ganada([ITEM])  # ITEM_OPT NO contratado
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])
		s6 = self._task_for(res["project"], "_SCHED_S6")
		deps = frappe.get_all("Task Depends On", filters={"parent": s6.name}, pluck="task")
		self.assertEqual(deps, [], "La dependencia a un Scope Item no contratado se omite")

	# ── Roll-up de fase ──

	def test_phase_parent_rollup(self):
		q = self._make_ganada([ITEM])
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])
		parent = frappe.db.get_value(
			"Task", {"project": res["project"], "proposal_phase": "SCHEDP1", "is_group": 1}, "name"
		)
		p = frappe.db.get_value("Task", parent, ["exp_start_date", "exp_end_date"], as_dict=True)
		start = getdate(frappe.utils.today())
		# Fase 1 hijas: S1(0..1), S2(2..4), S3(-5..-5), S7(5..6).
		# Min inicio = S3 (start-5); max fin = S7 (start+6, cadena S1→S2→S7).
		self.assertEqual(getdate(p.exp_start_date), add_days(start, -5))
		self.assertEqual(getdate(p.exp_end_date), add_days(start, 6))

	# ── Reintento tras ejecución parcial ──

	def test_retry_after_partial_completes_without_duplicates(self):
		q = self._make_ganada([ITEM])
		res = create_project_from_quotation(q.name)
		project = res["project"]
		self.__class__._projects.append(project)
		total = frappe.db.count("Task", {"project": project})
		# Simular fallo parcial: borrar la Task aislada S4 (hito, sin deps ni dependientes) y su enlace.
		s4 = self._task_for(project, "_SCHED_S4")
		parent_name = frappe.db.get_value("Task", s4.name, "parent_task")
		qsi = s4.source_quotation_scope_item
		frappe.db.set_value("Quotation Scope Item", qsi, "project_task", None, update_modified=False)
		frappe.delete_doc("Task", s4.name, force=True, ignore_permissions=True)
		# ERPNext liga cada hija en el depends_on de su Task-fase padre (populate_depends_on); el
		# borrado forzado deja esa fila colgada. Se limpia para simular un estado 'faltante' coherente
		# (equivalente a un borrado por UI, que sí depura el padre).
		if parent_name and frappe.db.exists("Task", parent_name):
			parent = frappe.get_doc("Task", parent_name)
			parent.set("depends_on", [r for r in parent.depends_on if frappe.db.exists("Task", r.task)])
			parent.save(ignore_permissions=True)
		self.assertEqual(frappe.db.count("Task", {"project": project}), total - 1)
		# Reintento: recrea SOLO la faltante, sin duplicar.
		res2 = create_project_from_quotation(q.name)
		self.assertEqual(res2["tasks_created"], 1)
		self.assertEqual(frappe.db.count("Task", {"project": project}), total)
		# S4 recreada como hito con su fecha; y las dependencias existentes (S2→S1) siguen intactas.
		s4b = self._task_for(project, "_SCHED_S4")
		self.assertEqual(int(s4b.is_milestone), 1)
		s2 = self._task_for(project, "_SCHED_S2")
		s1 = self._task_for(project, "_SCHED_S1")
		deps = frappe.get_all("Task Depends On", filters={"parent": s2.name}, pluck="task")
		self.assertIn(s1.name, deps)

	# ── Scope Item sin planeación PMO ──

	def test_no_pmo_config_no_invented_dates(self):
		code = "_SCHED_NOPMO"
		if not frappe.db.exists("Scope Item", code):
			frappe.get_doc(
				{
					"doctype": "Scope Item",
					"code": code,
					"title": code,
					"sequence": 70,
					"erpnext_item": ITEM_OPT,
					"phase": "SCHEDP1",
					"enabled": 1,
					"visible_in_proposal": 1,
					"estimated_hours": 2,
				}
			).insert(ignore_permissions=True)
		q = self._make_ganada([ITEM_OPT])
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])
		t = self._task_for(res["project"], code)
		self.assertIsNone(t.exp_start_date, "Sin PMO no se inventan fechas")
		self.assertIsNone(t.exp_end_date)

	# ── Cadena de varias dependencias ──

	def test_multi_dependency_chain(self):
		q = self._make_ganada([ITEM])
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])
		start = getdate(frappe.utils.today())
		# Cadena S1(offset "0") → S2(dep S1, dur 3) → S7(dep S2, dur 2).
		s2 = self._task_for(res["project"], "_SCHED_S2")
		s7 = self._task_for(res["project"], "_SCHED_S7")
		self.assertEqual(getdate(s2.exp_end_date), add_days(start, 4))
		# S7 sin offset: inicio = fin(S2)+1 = start+5; dur 2 → fin start+6.
		self.assertEqual(getdate(s7.exp_start_date), add_days(start, 5))
		self.assertEqual(getdate(s7.exp_end_date), add_days(start, 6))
		deps = frappe.get_all("Task Depends On", filters={"parent": s7.name}, pluck="task")
		self.assertIn(s2.name, deps)

	# ── Distinción vacío vs "0" en BD y snapshot ──

	def test_offset_empty_vs_zero_distinct_in_db_and_snapshot(self):
		# Maestro: S1 offset "0" (explícito) vs S5 sin offset (NULL) — distintos en BD.
		self.assertEqual(frappe.db.get_value("Scope Item", "_SCHED_S1", "planned_start_offset_days"), "0")
		self.assertIsNone(frappe.db.get_value("Scope Item", "_SCHED_S5", "planned_start_offset_days"))
		q = self._make_ganada([ITEM])
		# Snapshot congelado en Quotation Scope Item: "0" vs NULL, distintos.
		s1 = next(r for r in q.quotation_scope_items if r.code == "_SCHED_S1")
		s5 = next(r for r in q.quotation_scope_items if r.code == "_SCHED_S5")
		self.assertEqual(s1.planned_start_offset_days, "0")
		self.assertIn(s5.planned_start_offset_days, (None, ""))
		# Programación: "0" → inicia en la fecha del proyecto; vacío raíz → sin fecha.
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])
		start = getdate(frappe.utils.today())
		self.assertEqual(getdate(self._task_for(res["project"], "_SCHED_S1").exp_start_date), start)
		self.assertIsNone(self._task_for(res["project"], "_SCHED_S5").exp_start_date)

	# ── Validación: offset no entero rechazado ──

	def test_offset_reject_non_integer(self):
		from frappe.exceptions import ValidationError

		try:
			with self.assertRaises(ValidationError):
				frappe.get_doc(
					{
						"doctype": "Scope Item",
						"code": "_SCHED_BADOFF",
						"title": "bad",
						"sequence": 99,
						"enabled": 1,
						"planned_start_offset_days": "abc",
					}
				).insert(ignore_permissions=True)
		finally:
			if frappe.db.exists("Scope Item", "_SCHED_BADOFF"):
				frappe.delete_doc("Scope Item", "_SCHED_BADOFF", force=True, ignore_permissions=True)
