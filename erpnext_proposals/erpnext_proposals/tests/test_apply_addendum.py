"""Tests — `apply_addendum_to_project` (issue #59): aplicar una Quotation/Addendum **Ganada** a un
Project **existente** utilizando la lógica propia de `erpnext_proposals`.

Cubre: reuse del Project + materialización de Tasks de B conservando las de A; idempotencia; garantía de
que el path de addendum **nunca crea Project**; ausencia de `frappe.db.commit()` interno en ese path;
coherencia company/customer; `proposal_project` (vacío/igual/distinto); guards comerciales reutilizados
(`assert_can_create_project`); separación de permisos (WRITE sobre Project, sin exigir Proposals Manager).

**Apply-split (Change Control v2 B2, ADR-0019 §7.1):** Fase 1 SIEMPRE asocia + sincroniza economía; Fase 2
materializa Tasks SOLO si hay scope ejecutable. Cubre: addenda sin scope ejecutable (0 Tasks); solo Required
Items; net_total == 0; delta contractual $0 (autorizado sin cambio); idempotencia sin scope; y atomicidad por
rollback de la transacción externa ante fallo en la fase económica o en la materialización (sin commit interno).
"""

import unittest

import frappe
from frappe.exceptions import PermissionError as FrappePermissionError
from frappe.exceptions import ValidationError
from frappe.utils import flt

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
from erpnext_proposals.erpnext_proposals.utils import project as project_mod
from erpnext_proposals.erpnext_proposals.utils.project import (
	apply_addendum_to_project,
	create_project_from_quotation,
)

TEMPLATE = "_ADD Template"
ITEM = "_ADD Item"
# Item SIN Scope Items de catálogo asociados → una addenda construida sobre él genera 0 filas de scope
# ejecutable (apply-split B2: económica-only / solo Required / delta $0 / contractual).
ITEM_NS = "_ADD Item NoScope"
CO_B = "_ADD Co B"
CO_B_ABBR = "_ADDB"
CUST_A = "_ADD Cust A"
CUST_B = "_ADD Cust B"


class TestApplyAddendum(unittest.TestCase):
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
		for cust in (CUST_A, CUST_B):
			if not frappe.db.exists("Customer", cust):
				frappe.get_doc(
					{"doctype": "Customer", "customer_name": cust, "customer_group": cg, "territory": terr}
				).insert(ignore_permissions=True)
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		for code in (ITEM, ITEM_NS):
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
		for i, (code, phase) in enumerate(
			[("_ADD_S1", "DISC"), ("_ADD_S2", "DISC"), ("_ADD_S3", "IMPL")], start=1
		):
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
		# 2ª Company para el test de company mismatch.
		cls.company_b = cls._ensure_company_b()
		cls.cc_b = get_test_cost_center(cls.company_b)

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
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_ADD_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		cleanup_test_phases(getattr(cls, "_phases", None))
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		super().tearDownClass()

	# ── Helpers ──────────────────────────────────────────────────────────────

	def _quotation(
		self,
		company,
		cc,
		customer,
		ganada=True,
		group=None,
		addendum=False,
		item=ITEM,
		rate=1000,
		required=None,
	):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": customer,
				"proposal_group": group or ("ADD-" + frappe.generate_hash(length=6)),
				"company": company,
				"currency": "MXN",
				"selling_price_list": self.price_list,
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": cc,
				"proposal_title": "ADD " + frappe.generate_hash(length=4),
				"items": [{"item_code": item, "item_name": item, "qty": 1, "rate": rate, "uom": "Nos"}],
				"required_items": [{"item": c, "qty": 1, "uom": "Nos"} for c in (required or [])],
			}
		)
		if addendum:
			# Grupo reservado ROOT-ADD-NN: solo se admite con el flag transitorio de creación de addenda.
			doc.flags.from_addendum_creation = True
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._q.append(doc.name)
		if ganada:
			doc.reload()
			doc.flags.ignore_mandatory = True
			doc.flags.ignore_links = True
			doc.submit()  # before_submit → freeze_proposal + assert_economic_snapshot_complete
			frappe.db.set_value("Quotation", doc.name, "workflow_state", "Ganada", update_modified=False)
		return frappe.get_doc("Quotation", doc.name)

	def _base_project(self):
		a = self._quotation(self.company, self.cc, CUST_A)
		res = create_project_from_quotation(a.name)
		self.__class__._p.append(res["project"])
		return a, res["project"]

	def _addendum(self, root_doc, company=None, cc=None, customer=CUST_A, ganada=True, seq=1):
		"""Addenda canónica ``ROOT-ADD-NN`` del grupo de ``root_doc`` (Opción A: solo addendas se aplican).
		Construida sobre ``ITEM`` (ligado a Scope Items de catálogo) → SÍ tiene scope ejecutable."""
		grp = f"{root_doc.proposal_group}-ADD-{seq:02d}"
		return self._quotation(
			company or self.company, cc or self.cc, customer, ganada=ganada, group=grp, addendum=True
		)

	def _addendum_noscope(self, root_doc, seq=1, rate=1000, required=None):
		"""Addenda canónica SIN scope ejecutable (apply-split B2): construida sobre ``ITEM_NS`` (sin Scope
		Items de catálogo) → 0 filas ejecutables. ``rate=0`` la vuelve un delta económico $0; ``required``
		agrega Proposal Required Items (costo externo por el motor económico, sin generar Tasks)."""
		grp = f"{root_doc.proposal_group}-ADD-{seq:02d}"
		return self._quotation(
			self.company,
			self.cc,
			CUST_A,
			ganada=True,
			group=grp,
			addendum=True,
			item=ITEM_NS,
			rate=rate,
			required=required,
		)

	def _tasks(self, project):
		return set(frappe.get_all("Task", filters={"project": project}, pluck="name"))

	@classmethod
	def _ensure_user(cls, email, roles):
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": email.split("@")[0],
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		u = frappe.get_doc("User", email)
		existing = {r.role for r in u.roles}
		add = [r for r in roles if frappe.db.exists("Role", r) and r not in existing]
		if add:
			u.add_roles(*add)
		return email

	# ── Tests ────────────────────────────────────────────────────────────────

	def test_apply_adds_tasks_reuses_project(self):
		a, proj = self._base_project()
		a_tasks = self._tasks(proj)
		n_projects = frappe.db.count("Project")
		b = self._addendum(a)
		res = apply_addendum_to_project(b.name, proj)
		self.assertEqual(res["project"], proj)
		self.assertEqual(frappe.db.get_value("Quotation", b.name, "proposal_project"), proj)
		self.assertEqual(frappe.db.count("Project"), n_projects, "no debe crear Project")
		now = self._tasks(proj)
		self.assertTrue(a_tasks.issubset(now), "Tasks de A preservadas")
		self.assertGreater(len(now), len(a_tasks), "Tasks de B agregadas")

	def test_second_application_idempotent(self):
		a, proj = self._base_project()
		b = self._addendum(a)
		apply_addendum_to_project(b.name, proj)
		after1 = self._tasks(proj)
		res2 = apply_addendum_to_project(b.name, proj)
		self.assertEqual(after1, self._tasks(proj), "2ª aplicación no crea Tasks nuevas")
		self.assertEqual(res2["tasks_created"], 0)

	def test_addendum_never_creates_project(self):
		a, proj = self._base_project()
		n = frappe.db.count("Project")
		b = self._addendum(a)
		apply_addendum_to_project(b.name, proj)
		self.assertEqual(frappe.db.count("Project"), n, "el path de addendum nunca crea Project")

	def test_normal_group_rejected(self):
		"""Opción A: una Quotation de grupo NORMAL no puede aplicarse a un Project existente."""
		_a, proj = self._base_project()
		b = self._quotation(self.company, self.cc, CUST_A)  # grupo normal, NO addenda
		with self.assertRaises(ValidationError):
			apply_addendum_to_project(b.name, proj)

	def test_project_must_exist(self):
		a, _proj = self._base_project()
		b = self._addendum(a)
		with self.assertRaises(ValidationError):
			apply_addendum_to_project(b.name, "PROJ-NO-EXISTE-ADD")

	def test_company_mismatch(self):
		a, proj = self._base_project()  # company A
		b = self._addendum(a, company=self.company_b, cc=self.cc_b)  # addenda con company B
		with self.assertRaises(ValidationError):
			apply_addendum_to_project(b.name, proj)

	def test_customer_mismatch(self):
		a, proj = self._base_project()  # customer A
		b = self._addendum(a, customer=CUST_B)  # addenda con customer B
		with self.assertRaises(ValidationError):
			apply_addendum_to_project(b.name, proj)

	def test_wrong_project_rejected(self):
		"""Una addenda solo se aplica al Project de su root; a otro Project falla cerrado."""
		a, _proj = self._base_project()
		_a2, proj2 = self._base_project()
		b = self._addendum(a)
		with self.assertRaises(ValidationError):
			apply_addendum_to_project(b.name, proj2)

	def test_guard_not_ganada(self):
		a, proj = self._base_project()
		b = self._addendum(a, ganada=False)  # Borrador
		with self.assertRaises(ValidationError):
			apply_addendum_to_project(b.name, proj)

	def test_no_internal_commit_in_addendum_path(self):
		a, proj = self._base_project()  # este create SÍ commitea (antes del patch)
		b = self._addendum(a)
		calls = {"n": 0}
		orig = frappe.db.commit

		def _counting_commit(*a, **k):
			calls["n"] += 1

		frappe.db.commit = _counting_commit
		try:
			apply_addendum_to_project(b.name, proj)
		finally:
			frappe.db.commit = orig
		self.assertEqual(calls["n"], 0, "el path de addendum no debe hacer frappe.db.commit()")

	# ── B2 apply-split: Fase 1 (SIEMPRE asociar + sync) / Fase 2 (SOLO si hay scope ejecutable) ────────

	def test_no_exec_scope_associates_syncs_zero_tasks(self):
		"""#2 Addenda SIN scope ejecutable: se asocia, sincroniza economía y crea 0 Tasks (Fase 2 omitida),
		sin fallar por validación de scope/fase."""
		a, proj = self._base_project()
		before = self._tasks(proj)
		b = self._addendum_noscope(a, seq=1)
		res = apply_addendum_to_project(b.name, proj)
		self.assertEqual(res["project"], proj)
		self.assertEqual(res["tasks_created"], 0)
		self.assertFalse(res["scope_materialized"])
		self.assertEqual(frappe.db.get_value("Quotation", b.name, "proposal_project"), proj)
		self.assertEqual(self._tasks(proj), before, "no debe crear Tasks")

	def test_only_required_items_applies_zero_tasks(self):
		"""#3 Addenda solo con Required Items (costo externo por el motor económico): se aplica, 0 Tasks."""
		a, proj = self._base_project()
		before = self._tasks(proj)
		b = self._addendum_noscope(a, seq=2, rate=0, required=[ITEM_NS])
		res = apply_addendum_to_project(b.name, proj)
		self.assertEqual(res["tasks_created"], 0)
		self.assertFalse(res["scope_materialized"])
		self.assertEqual(frappe.db.get_value("Quotation", b.name, "proposal_project"), proj)
		self.assertEqual(self._tasks(proj), before)

	def test_net_total_zero_addenda_applies(self):
		"""#4 Addenda económica con net_total == 0: puede aplicarse; 0 Tasks; economía se recomputa."""
		a, proj = self._base_project()
		b = self._addendum_noscope(a, seq=3, rate=0)
		self.assertEqual(flt(frappe.db.get_value("Quotation", b.name, "net_total")), 0.0)
		res = apply_addendum_to_project(b.name, proj)
		self.assertEqual(res["tasks_created"], 0)
		self.assertEqual(frappe.db.get_value("Quotation", b.name, "proposal_project"), proj)

	def test_contractual_delta_zero_authorized_unchanged(self):
		"""#5 Addenda puramente contractual / delta $0: queda aplicada aunque el autorizado no cambie."""
		a, proj = self._base_project()
		before = flt(frappe.db.get_value("Project", proj, "estimated_costing"))
		b = self._addendum_noscope(a, seq=4, rate=0)  # sin costo ni revenue → delta $0
		res = apply_addendum_to_project(b.name, proj)
		after = flt(frappe.db.get_value("Project", proj, "estimated_costing"))
		self.assertEqual(after, before, "un delta $0 no cambia el costo autorizado")
		self.assertEqual(res["tasks_created"], 0)
		self.assertEqual(frappe.db.get_value("Quotation", b.name, "proposal_project"), proj)

	def test_no_scope_reapplication_idempotent(self):
		"""#8 Reaplicar una addenda sin scope es idempotente (no duplica economía ni Tasks)."""
		a, proj = self._base_project()
		b = self._addendum_noscope(a, seq=5)
		apply_addendum_to_project(b.name, proj)
		before = self._tasks(proj)
		res2 = apply_addendum_to_project(b.name, proj)
		self.assertEqual(res2["tasks_created"], 0)
		self.assertEqual(self._tasks(proj), before)
		self.assertEqual(frappe.db.get_value("Quotation", b.name, "proposal_project"), proj)

	def test_failure_during_economic_sync_rolls_back(self):
		"""#6 Fallo durante la sincronización económica (Fase 1): tras el rollback de la transacción externa
		no debe quedar `proposal_project` ni materialización parcial."""
		from erpnext_proposals.erpnext_proposals.utils import project_economics as pe_mod

		a, proj = self._base_project()  # committed
		before_tasks = self._tasks(proj)
		b = self._addendum(a)  # exec-scope: el sync corre ANTES de materializar
		orig = pe_mod.sync_project_authorized_cost

		def _boom(*a, **k):
			raise RuntimeError("sync boom")

		pe_mod.sync_project_authorized_cost = _boom
		try:
			with self.assertRaises(RuntimeError):
				apply_addendum_to_project(b.name, proj)
		finally:
			pe_mod.sync_project_authorized_cost = orig
			frappe.db.rollback()
		self.assertFalse(
			frappe.db.get_value("Quotation", b.name, "proposal_project"),
			"una sync económica fallida no debe dejar proposal_project asociado",
		)
		self.assertEqual(self._tasks(proj), before_tasks, "no debe quedar materialización parcial")

	def test_failure_during_materialization_rolls_back(self):
		"""#7 Fallo durante la materialización de Tasks (Fase 2, DESPUÉS de la fase económica): toda la
		operación se revierte con la transacción externa (sin commit interno) — ni asociación ni Tasks."""
		a, proj = self._base_project()
		before_tasks = self._tasks(proj)
		b = self._addendum(a)  # exec-scope → Fase 2 corre
		orig = project_mod._materialize_scope_into_project

		def _boom(*a, **k):
			raise RuntimeError("materialize boom")

		project_mod._materialize_scope_into_project = _boom
		try:
			with self.assertRaises(RuntimeError):
				apply_addendum_to_project(b.name, proj)
		finally:
			project_mod._materialize_scope_into_project = orig
			frappe.db.rollback()
		self.assertFalse(
			frappe.db.get_value("Quotation", b.name, "proposal_project"),
			"un fallo de materialización tras la fase económica no debe dejar proposal_project asociado",
		)
		self.assertEqual(self._tasks(proj), before_tasks, "no debe quedar materialización parcial")

	def test_permission_write_required_and_no_proposals_manager(self):
		a, proj = self._base_project()
		b = self._addendum(a)
		writer = self._ensure_user("add-writer@example.com", ["Projects User"])
		reader = self._ensure_user("add-reader@example.com", ["Blogger"])
		if "Projects User" not in frappe.get_roles(writer):
			raise unittest.SkipTest("Rol 'Projects User' no disponible para probar permisos.")
		# Negativo: usuario sin WRITE sobre Project → PermissionError.
		frappe.set_user(reader)
		try:
			with self.assertRaises(FrappePermissionError):
				apply_addendum_to_project(b.name, proj)
		finally:
			frappe.set_user("Administrator")
		# Positivo: usuario con WRITE sobre Project pero SIN Proposals Manager → aplica.
		frappe.set_user(writer)
		try:
			self.assertNotIn("Proposals Manager", frappe.get_roles(writer))
			res = apply_addendum_to_project(b.name, proj)
			self.assertEqual(res["project"], proj)
		finally:
			frappe.set_user("Administrator")


if __name__ == "__main__":
	unittest.main()
