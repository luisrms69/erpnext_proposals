"""Tests — contrato canónico de addendas ``<ROOT>-ADD-<NN>`` (utils.addendum).

Cubre la semántica centralizada y su integración:
- parsing/reconocimiento/resolución de root (única fuente de la semántica);
- `create_addendum_quotation`: creación ATÓMICA, secuencia por-root, lock por-root, contenido delta
  (NO copia alcance/items/proposal_project/template del root);
- namespace reservado ``-ADD-NN`` fail-closed (captura manual bloqueada; primitive y versionado permitidos);
- exclusión estructural del auto-Project para addendas (aunque el toggle esté ON);
- `apply_addendum_to_project` para addendas: resuelve el Project raíz (nunca por nombre), exige match,
  materializa solo el alcance de esa addenda, idempotente, ADD-01/ADD-02 independientes.
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
from erpnext_proposals.erpnext_proposals.utils import workflow_validations as wfv_mod
from erpnext_proposals.erpnext_proposals.utils.addendum import (
	create_addendum_quotation,
	is_addendum_group,
	parse_addendum_group,
	resolve_root_group,
	resolve_root_project,
)
from erpnext_proposals.erpnext_proposals.utils.project import (
	apply_addendum_to_project,
	auto_create_project_on_won,
	create_project_from_quotation,
)

TEMPLATE = "_ADX Template"
ITEM = "_ADX Item"
CUST = "_ADX Cust"


class TestAddendumContract(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._q = []
		cls._p = []
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
		for i, (code, phase) in enumerate([("_ADX_S1", "DISC"), ("_ADX_S2", "IMPL")], start=1):
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
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_ADX_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		cleanup_test_phases(getattr(cls, "_phases", None))
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		super().tearDownClass()

	# ── Helpers ──────────────────────────────────────────────────────────────

	def _quotation(self, group, ganada=True, with_scope=True, addendum=False):
		"""Crea una Quotation. `addendum=True` habilita el flag transitorio para permitir un grupo
		reservado -ADD-NN (simula el delta que la preventa edita tras `create_addendum_quotation`)."""
		data = {
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": CUST,
			"proposal_group": group,
			"company": self.company,
			"currency": "MXN",
			"selling_price_list": self.price_list,
			"transaction_date": frappe.utils.today(),
			"proposal_cost_center": self.cc,
			"proposal_title": "ADX " + frappe.generate_hash(length=4),
		}
		if with_scope:
			data["proposal_template"] = TEMPLATE
			data["items"] = [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}]
		doc = frappe.get_doc(data)
		if addendum:
			doc.flags.from_addendum_creation = True
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._q.append(doc.name)
		if ganada:
			doc.reload()
			doc.flags.ignore_mandatory = True
			doc.flags.ignore_links = True
			doc.submit()
			frappe.db.set_value("Quotation", doc.name, "workflow_state", "Ganada", update_modified=False)
		return frappe.get_doc("Quotation", doc.name)

	def _root_project(self):
		"""Grupo raíz normal + su Project (la Ganada del root queda con proposal_project)."""
		grp = "ROOT" + frappe.generate_hash(length=6)
		root = self._quotation(grp)
		res = create_project_from_quotation(root.name)
		self.__class__._p.append(res["project"])
		return grp, root, res["project"]

	def _tasks(self, project):
		return set(frappe.get_all("Task", filters={"project": project}, pluck="name"))

	def _track(self, name):
		self.__class__._q.append(name)
		return name

	# ── Parsing / reconocimiento ──────────────────────────────────────────────

	def test_is_and_parse_addendum_group(self):
		self.assertTrue(is_addendum_group("ROOT-ADD-01"))
		self.assertTrue(is_addendum_group("a-b-c-ADD-12"))
		self.assertFalse(is_addendum_group("ROOT"))
		self.assertFalse(is_addendum_group("ROOT-ADD-"))  # sin dígitos
		self.assertFalse(is_addendum_group("ROOT-ADD-CAMPAIGN"))  # sufijo no numérico
		self.assertFalse(is_addendum_group(""))
		self.assertFalse(is_addendum_group(None))
		self.assertEqual(parse_addendum_group("PROJ-2024-ADD-03"), ("PROJ-2024", 3))
		self.assertIsNone(parse_addendum_group("PROJ-2024"))

	def test_resolve_root_group(self):
		self.assertEqual(resolve_root_group("ROOT"), "ROOT")
		self.assertEqual(resolve_root_group("ROOT-ADD-01"), "ROOT")
		self.assertEqual(resolve_root_group("ROOT-ADD-07"), "ROOT")
		# Anidado (defensivo): sube hasta el root real.
		self.assertEqual(resolve_root_group("ROOT-ADD-01-ADD-02"), "ROOT")

	# ── Resolución del Project raíz ───────────────────────────────────────────

	def test_resolve_root_project_from_won(self):
		grp, _root, proj = self._root_project()
		self.assertEqual(resolve_root_project(grp), proj)

	def test_resolve_root_project_without_won_raises(self):
		grp = "ROOTNW" + frappe.generate_hash(length=5)
		self._quotation(grp, ganada=False)  # solo Borrador → sin Ganada vigente
		with self.assertRaises(ValidationError):
			resolve_root_project(grp)

	# ── create_addendum_quotation: atómica, secuencia, contenido delta ────────

	def test_create_addendum_sequence_and_empty_delta(self):
		grp, root, _proj = self._root_project()
		a1 = frappe.get_doc("Quotation", self._track(create_addendum_quotation(root.name)))
		self.assertEqual(a1.proposal_group, f"{grp}-ADD-01")
		self.assertEqual(a1.proposal_version, 1)
		# Contenido delta: sin items, sin scope, sin template, sin proposal_project.
		self.assertEqual(len(a1.items), 0, "la addenda NO copia items originales")
		self.assertEqual(len(a1.quotation_scope_items), 0, "la addenda NO copia Scope Items originales")
		self.assertFalse(a1.proposal_template, "la addenda NO hereda el template (no regenera alcance)")
		self.assertFalse(a1.proposal_project, "la addenda NO hereda proposal_project")
		# Contexto comercial seguro heredado.
		self.assertEqual(a1.company, self.company)
		self.assertEqual(a1.party_name, CUST)
		self.assertEqual(a1.currency, "MXN")
		# Segunda addenda → ADD-02.
		a2 = frappe.get_doc("Quotation", self._track(create_addendum_quotation(root.name)))
		self.assertEqual(a2.proposal_group, f"{grp}-ADD-02")

	def test_create_addendum_from_addendum_reference_resolves_root(self):
		"""Pasar una addenda como referencia sube al root real: la nueva sigue siendo ROOT-ADD-NN plano."""
		grp, root, _proj = self._root_project()
		a1 = create_addendum_quotation(root.name)
		self._track(a1)
		a2 = frappe.get_doc("Quotation", self._track(create_addendum_quotation(a1)))
		self.assertEqual(a2.proposal_group, f"{grp}-ADD-02", "resuelve root, no anida")

	def test_create_addendum_lock_is_root_scoped(self):
		"""El lock FOR UPDATE se toma sobre el ROOT, no sobre el nombre concreto recibido."""
		grp, root, _proj = self._root_project()
		a1 = create_addendum_quotation(root.name)  # crea ADD-01
		self._track(a1)
		captured = []
		orig = frappe.db.sql

		def _spy(query, values=None, *a, **k):
			if isinstance(query, str) and "FOR UPDATE" in query:
				captured.append(values)
			return orig(query, values, *a, **k)

		frappe.db.sql = _spy
		try:
			# Referencia = la addenda ADD-01; el lock debe tomarse sobre el ROOT `grp`.
			a2 = create_addendum_quotation(a1)
			self._track(a2)
		finally:
			frappe.db.sql = orig
		self.assertTrue(captured, "debe emitirse un SELECT ... FOR UPDATE")
		self.assertIn(grp, captured, "el lock debe tomarse sobre el grupo ROOT, no sobre la addenda recibida")

	# ── Namespace reservado (fail-closed) ─────────────────────────────────────

	def test_manual_reserved_group_blocked(self):
		with self.assertRaises(ValidationError):
			self._quotation("MANUAL-ADD-01", ganada=False, with_scope=False, addendum=False)

	def test_primitive_reserved_group_allowed(self):
		_grp, root, _proj = self._root_project()
		name = create_addendum_quotation(root.name)  # usa el flag autorizado internamente
		self._track(name)
		self.assertTrue(frappe.db.exists("Quotation", name))

	def test_legit_addendum_versioning_allowed(self):
		"""Una revisión de una addenda (previous_proposal + flag de versionado) conserva el grupo -ADD-NN."""
		from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import (
			create_new_proposal_version,
		)

		grp, root, _proj = self._root_project()
		add = frappe.get_doc("Quotation", self._track(create_addendum_quotation(root.name)))
		# Darle alcance y llevarla a Rechazada para poder versionar.
		add.proposal_template = TEMPLATE
		add.append("items", {"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 500, "uom": "Nos"})
		add.save(ignore_permissions=True)
		add.reload()
		add.flags.ignore_mandatory = True
		add.submit()
		frappe.db.set_value("Quotation", add.name, "workflow_state", "Rechazada", update_modified=False)
		new_name = create_new_proposal_version(add.name, reason="ajuste", summary="s")
		self._track(new_name)
		# La nueva versión conserva EXACTAMENTE el grupo de la addenda.
		self.assertEqual(frappe.db.get_value("Quotation", new_name, "proposal_group"), f"{grp}-ADD-01")

	# ── Exclusión estructural del auto-Project ────────────────────────────────

	def test_auto_project_job_creates_for_normal(self):
		_grp, _root, _proj = self._root_project()
		# Simular otra Ganada normal (mismo customer/company) sin project aún y correr el job.
		grp2 = "ROOTN" + frappe.generate_hash(length=5)
		q = self._quotation(grp2)
		auto_create_project_on_won(q.name)
		self.assertTrue(
			frappe.db.get_value("Quotation", q.name, "proposal_project"), "normal SÍ crea Project"
		)
		self.__class__._p.append(frappe.db.get_value("Quotation", q.name, "proposal_project"))

	def test_auto_project_job_skips_addendum(self):
		_grp, _root, _proj = self._root_project()
		add = self._quotation(f"{_grp}-ADD-01", addendum=True)  # addenda Ganada con alcance
		n_before = frappe.db.count("Project")
		auto_create_project_on_won(add.name)  # toggle-agnóstico: el job debe excluir addendas
		self.assertFalse(
			frappe.db.get_value("Quotation", add.name, "proposal_project"),
			"una addenda NUNCA crea Project por el job de auto-creación",
		)
		self.assertEqual(frappe.db.count("Project"), n_before)

	def test_enqueue_gate_skips_addendum(self):
		"""`_maybe_enqueue_auto_project` no encola para una addenda (exclusión estructural al encolar)."""
		_grp, _root, _proj = self._root_project()
		add = self._quotation(f"{_grp}-ADD-01", addendum=True)
		calls = []
		orig = frappe.enqueue

		def _spy(*a, **k):
			calls.append((a, k))

		frappe.enqueue = _spy
		try:
			wfv_mod._maybe_enqueue_auto_project(add)
		finally:
			frappe.enqueue = orig
		self.assertEqual(calls, [], "no debe encolar auto-creación de Project para una addenda")

	def test_create_project_button_blocked_for_addendum(self):
		_grp, _root, _proj = self._root_project()
		add = self._quotation(f"{_grp}-ADD-01", addendum=True)
		with self.assertRaises(ValidationError):
			create_project_from_quotation(add.name)

	# ── apply_addendum_to_project: addenda → Project raíz ─────────────────────

	def test_apply_addendum_materializes_only_its_scope(self):
		grp, _root, proj = self._root_project()
		root_tasks = self._tasks(proj)
		add = self._quotation(f"{grp}-ADD-01", addendum=True)
		res = apply_addendum_to_project(add.name, proj)
		self.assertEqual(res["project"], proj, "reutiliza el Project raíz, no crea otro")
		now = self._tasks(proj)
		self.assertTrue(root_tasks.issubset(now), "Tasks del root preservadas")
		self.assertGreater(len(now), len(root_tasks), "se agregan las Tasks de la addenda")
		self.assertEqual(frappe.db.get_value("Quotation", add.name, "proposal_project"), proj)

	def test_apply_addendum_wrong_project_rejected(self):
		grp, _root, _proj = self._root_project()
		_grp2, _root2, proj2 = self._root_project()  # otro Project distinto
		add = self._quotation(f"{grp}-ADD-01", addendum=True)
		with self.assertRaises(ValidationError):
			apply_addendum_to_project(add.name, proj2)  # no coincide con el Project raíz de grp

	def test_apply_addendum_idempotent(self):
		grp, _root, proj = self._root_project()
		add = self._quotation(f"{grp}-ADD-01", addendum=True)
		apply_addendum_to_project(add.name, proj)
		after1 = self._tasks(proj)
		res2 = apply_addendum_to_project(add.name, proj)
		self.assertEqual(after1, self._tasks(proj), "reaplicar la misma addenda no duplica Tasks")
		self.assertEqual(res2["tasks_created"], 0)

	def test_add01_and_add02_independent_and_additive(self):
		grp, _root, proj = self._root_project()
		root_tasks = self._tasks(proj)
		add1 = self._quotation(f"{grp}-ADD-01", addendum=True)
		add2 = self._quotation(f"{grp}-ADD-02", addendum=True)
		apply_addendum_to_project(add1.name, proj)
		after_add1 = self._tasks(proj)
		apply_addendum_to_project(add2.name, proj)
		after_add2 = self._tasks(proj)
		self.assertTrue(root_tasks.issubset(after_add1))
		self.assertTrue(after_add1.issubset(after_add2), "ADD-02 agrega sin quitar lo de root/ADD-01")
		self.assertGreater(len(after_add2), len(after_add1), "ADD-02 agrega su propio alcance")
		# Cadenas de versionado independientes: cada grupo tiene su propia única viva.
		self.assertNotEqual(add1.proposal_group, add2.proposal_group)
		from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import (
			get_live_proposal_for_group,
		)

		self.assertEqual(get_live_proposal_for_group(add1.proposal_group), add1.name)
		self.assertEqual(get_live_proposal_for_group(add2.proposal_group), add2.name)

	def test_no_internal_commit_in_addendum_path(self):
		grp, _root, proj = self._root_project()
		add = self._quotation(f"{grp}-ADD-01", addendum=True)
		calls = {"n": 0}
		orig = frappe.db.commit

		def _counting_commit(*a, **k):
			calls["n"] += 1

		frappe.db.commit = _counting_commit
		try:
			apply_addendum_to_project(add.name, proj)
		finally:
			frappe.db.commit = orig
		self.assertEqual(calls["n"], 0, "el path de addenda no debe hacer frappe.db.commit()")


if __name__ == "__main__":
	unittest.main()
