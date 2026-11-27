"""Regresión — Project-on-Won en propuestas VERSIONADAS (defecto: scope heredado con source_row=NULL).

Contexto del defecto: `create_new_proposal_version` copia `quotation_scope_items` pero EXCLUYE `source_row`
(para no arrastrar names obsoletos) e inserta con `skip_scope_generation`, por lo que la generación —que
derivaba `source_row`— no corre. Las filas quedaban con `source_row=NULL` y, al llegar la V2 a «Ganada»,
`auto_create_project_on_won` fallaba en `_item_parent_task(None)` con `MandatoryError: subject` → sin Project.

Fix:
- `_relink_inherited_scope_source_rows` (quotation.validate): re-vincula las filas heredadas a la fila
  origen ACTUAL del mismo item_code (names nuevos, nunca los obsoletos), preservando identidad por ocurrencia.
- `_item_parent_task` (project): defensa en profundidad — una fila sin source_row no rompe (subject nunca
  vacío) y agrupa por item_code (sin duplicados).

Cubre: V1 fresca crea Project (baseline, sin regresión); V2 re-vincula source_row y crea Project; una fila
con source_row ausente no provoca MandatoryError y agrupa correctamente.
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
from erpnext_proposals.erpnext_proposals.utils.project import (
	auto_create_project_on_won,
	create_project_from_quotation,
)
from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import create_new_proposal_version

TEMPLATE = "_VP Template"
SOLD = "_VP Sold"  # Item vendido (sin scope propio → satisface _validate_scope_for_project)
REQ = "_VP Req"  # Item requerido con scope interno (espejo de COORD-LICENCIAS)
CUST = "_VP Cust"
S1, S2 = "_VP_S1", "_VP_S2"


class TestVersionedProjectOnWon(unittest.TestCase):
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
		cls.uom = frappe.db.get_value("UOM", {"enabled": 1}, "name")
		if not cls.uom:
			raise unittest.SkipTest("No enabled UOM on test site.")
		ig = get_test_item_group()
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {}, "name")
		if not cg:
			raise unittest.SkipTest("No Customer Group on test site.")
		if not frappe.db.exists("Customer", CUST):
			frappe.get_doc(
				{"doctype": "Customer", "customer_name": CUST, "customer_group": cg, "territory": terr}
			).insert(ignore_permissions=True)
		for code, sales, purchase in ((SOLD, 1, 0), (REQ, 0, 1)):
			if not frappe.db.exists("Item", code):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_name": code,
						"item_group": ig,
						"stock_uom": cls.uom,
						"is_stock_item": 0,
						"is_sales_item": sales,
						"is_purchase_item": purchase,
					}
				).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "t"}
			).insert(ignore_permissions=True)
		# Scope interno del Item requerido (is_internal_cost_task; link legacy erpnext_item = REQ).
		for i, (code, phase) in enumerate([(S1, "DISC"), (S2, "IMPL")], start=1):
			if not frappe.db.exists("Scope Item", code):
				frappe.get_doc(
					{
						"doctype": "Scope Item",
						"code": code,
						"title": code,
						"sequence": i,
						"erpnext_item": REQ,
						"estimated_hours": 4,
						"enabled": 1,
						"visible_in_proposal": 0,
						"is_internal_cost_task": 1,
						"phase": phase,
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
		for code in (S1, S2):
			if frappe.db.exists("Scope Item", code):
				frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		cleanup_test_phases(getattr(cls, "_phases", None))
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		super().tearDownClass()

	# ── Helpers ──────────────────────────────────────────────────────────────

	def _make_v1(self):
		"""Crea una V1 submitted con un Item vendido + un Item requerido con scope interno, y la deja en
		estado Rechazada (prerrequisito para versionar)."""
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": CUST,
				"proposal_group": "VP-" + frappe.generate_hash(length=6),
				"company": self.company,
				"currency": "MXN",
				"selling_price_list": self.price_list,
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cc,
				"proposal_contract_term_months": 12,
				"proposal_title": "VP " + frappe.generate_hash(length=4),
				"items": [{"item_code": SOLD, "item_name": SOLD, "qty": 1, "rate": 1000, "uom": self.uom}],
				"required_items": [{"item": REQ, "qty": 1}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._q.append(doc.name)
		doc.reload()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		frappe.db.set_value("Quotation", doc.name, "workflow_state", "Rechazada", update_modified=False)
		return doc.name

	def _win_and_create(self, qname):
		frappe.db.set_value("Quotation", qname, "workflow_state", "Ganada", update_modified=False)
		auto_create_project_on_won(qname)
		proj = frappe.db.get_value("Quotation", qname, "proposal_project")
		if proj:
			self.__class__._p.append(proj)
		return proj

	def _scope_rows(self, qname):
		return frappe.get_all(
			"Quotation Scope Item",
			filters={"parent": qname},
			fields=["name", "item_code", "scope_item", "source_row", "source_type"],
		)

	# ── Tests ──────────────────────────────────────────────────────────────

	def test_1_v1_fresh_creates_project_baseline(self):
		"""Baseline (sin regresión): una V1 fresca genera el scope con source_row ligado al required row y
		crea su Project al ganar."""
		v1 = self._make_v1()
		rows = self._scope_rows(v1)
		self.assertTrue(rows, "la V1 debe materializar scope del Item requerido")
		req_row = frappe.get_doc("Quotation", v1).required_items[0].name
		for r in rows:
			self.assertEqual(r.source_row, req_row, "V1: source_row apunta al required row")
			self.assertEqual(r.source_type, "required")

	def test_2_v2_relinks_source_row_to_new_rows(self):
		"""La V2 versionada re-vincula source_row a SUS filas (no a las de la V1) — nunca NULL ni obsoleto."""
		v1 = self._make_v1()
		v1_req_row = frappe.get_doc("Quotation", v1).required_items[0].name
		v2 = create_new_proposal_version(v1, reason="regresión versionado")
		self.__class__._q.append(v2)
		v2_doc = frappe.get_doc("Quotation", v2)
		v2_req_row = v2_doc.required_items[0].name
		self.assertNotEqual(v2_req_row, v1_req_row, "la V2 tiene su propio required row (name nuevo)")
		rows = self._scope_rows(v2)
		self.assertTrue(rows, "la V2 hereda las filas de scope")
		for r in rows:
			self.assertTrue(r.source_row, f"V2: source_row NO debe quedar vacío (fila {r.name})")
			self.assertEqual(r.source_row, v2_req_row, "V2: source_row re-vinculado al required row de la V2")
			self.assertNotEqual(r.source_row, v1_req_row, "V2: no reutiliza el row obsoleto de la V1")

	def test_3_v2_won_creates_project_grouped(self):
		"""La V2 al llegar a «Ganada» crea el Project (ya no MandatoryError) y agrupa las Tasks bajo UN solo
		padre por ocurrencia del Item requerido (sin duplicados)."""
		v1 = self._make_v1()
		v2 = create_new_proposal_version(v1, reason="regresión versionado")
		self.__class__._q.append(v2)
		# create_new_proposal_version deja la V2 en Borrador: hay que someterla para poder ganarla.
		v2_doc = frappe.get_doc("Quotation", v2)
		v2_doc.flags.ignore_mandatory = True
		v2_doc.flags.ignore_links = True
		v2_doc.submit()
		proj = self._win_and_create(v2)
		self.assertTrue(proj and frappe.db.exists("Project", proj), "la V2 ganada debe crear su Project")
		parents = frappe.get_all("Task", filters={"project": proj, "is_group": 1}, fields=["name", "subject"])
		# Un padre por ocurrencia de Item: SOLD (operativo) + REQ (scope interno) = 2; ninguno con subject vacío.
		self.assertTrue(parents, "deben existir Tasks padre")
		for p in parents:
			self.assertTrue((p.subject or "").strip(), "ningún padre con subject vacío")
		req_parents = [p for p in parents if REQ in (p.subject or "")]
		self.assertEqual(len(req_parents), 1, "exactamente UN padre para el Item requerido (sin duplicados)")
		children = frappe.get_all(
			"Task", filters={"project": proj, "is_group": 0, "parent_task": req_parents[0].name}, pluck="name"
		)
		self.assertEqual(len(children), 2, "las 2 Tasks internas cuelgan del padre del Item requerido")

	def test_4_missing_source_row_does_not_raise(self):
		"""Defensa en profundidad: una fila de scope con source_row AUSENTE no provoca MandatoryError; el
		padre se arma con subject = item_code y agrupa en uno solo."""
		v1 = self._make_v1()
		# Simula el estado legacy no re-vinculado: vacía el source_row de las filas de scope del documento.
		for r in self._scope_rows(v1):
			frappe.db.set_value("Quotation Scope Item", r.name, "source_row", "", update_modified=False)
		frappe.db.set_value("Quotation", v1, "workflow_state", "Ganada", update_modified=False)
		# No debe lanzar MandatoryError: subject.
		create_project_from_quotation(v1)
		proj = frappe.db.get_value("Quotation", v1, "proposal_project")
		if proj:
			self.__class__._p.append(proj)
		self.assertTrue(
			proj and frappe.db.exists("Project", proj), "debe crear el Project pese a source_row vacío"
		)
		req_parents = frappe.get_all(
			"Task", filters={"project": proj, "is_group": 1, "subject": ["like", f"%{REQ}%"]}, pluck="name"
		)
		self.assertEqual(len(req_parents), 1, "un único padre por item_code aunque falte source_row")


if __name__ == "__main__":
	unittest.main()
