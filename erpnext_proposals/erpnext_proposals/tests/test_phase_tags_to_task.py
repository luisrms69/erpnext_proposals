"""Transferencia de Tags NATIVOS de Frappe: Proposal Phase -> su Task padre al crear el Project.

Verifica el mecanismo genérico e idempotente:
- La Task padre de la fase recibe EXACTAMENTE los Tags nativos de su Proposal Phase.
- Las Tasks hijas NO reciben esos Tags.
- No se escriben Tags en Item, Scope Item, Quotation ni Project por esta función.
- Un reintento no duplica Tags (ni en _user_tags ni en Tag Link).
- La Proposal Phase conserva sus Tags.

Datos ficticios; nunca contenido de cliente. Los nombres de Tags y el código de fase son locales al
test: el código de la app NO conoce ninguno (copia lo que la Proposal Phase tenga).
"""

import unittest

import frappe
from frappe.desk.doctype.tag.tag import DocTags

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils.project import create_project_from_quotation

TEMPLATE = "_Test TAG Template"
ITEM = "_Test TAG Item"
PHASE = "_TAGP1"
PHASE2 = "_TAGP2"  # sin Tags: su Task padre no debe recibir ninguno
TAGS = ["_TagServicioX", "_TagAreaY", "_TagAreaZ"]  # múltiples Tags (Servicio + varias Áreas)


def _tag_links(dt, dn):
	"""Conjunto de Tags nativos (Tag Link, almacén canónico) de un documento."""
	return set(frappe.get_all("Tag Link", filters={"document_type": dt, "document_name": dn}, pluck="tag"))


class TestPhaseTagsToTask(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_company, get_test_item_group

		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company found on test site.")
		cls._quotations = []
		cls._projects = []
		cls._created_fy = ensure_current_fiscal_year()

		for code, name, seq in ((PHASE, "Fase con tags", 10), (PHASE2, "Fase sin tags", 20)):
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
		# Tags nativos SOLO en la fase PHASE (varios); PHASE2 queda sin Tags.
		for t in TAGS:
			DocTags("Proposal Phase").add(PHASE, t)

		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {}, "name")
		if not frappe.db.exists("Customer", "_Test TAG Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test TAG Customer",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test TAG Customer"
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		ig = get_test_item_group()
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
		cls.cost_center = frappe.db.get_value("Cost Center", {"is_group": 0}, "name")

		# Dos Scope Items visibles: uno en la fase con tags, otro en la fase sin tags.
		cls._scope("_TAG_S1", PHASE, 10)
		cls._scope("_TAG_S2", PHASE2, 20)

	@classmethod
	def _scope(cls, code, phase, seq):
		if frappe.db.exists("Scope Item", code):
			return
		frappe.get_doc(
			{
				"doctype": "Scope Item",
				"code": code,
				"title": code,
				"sequence": seq,
				"erpnext_item": ITEM,
				"phase": phase,
				"enabled": 1,
				"visible_in_proposal": 1,
				"estimated_hours": 4,
				"planned_start_offset_days": "0",
				"planned_duration_days": 2,
				"is_milestone": 0,
			}
		).insert(ignore_permissions=True)

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
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_TAG_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		for code in (PHASE, PHASE2):
			if frappe.db.exists("Proposal Phase", code):
				frappe.delete_doc("Proposal Phase", code, force=True, ignore_permissions=True)
		for t in TAGS:
			if frappe.db.exists("Tag", t):
				frappe.delete_doc("Tag", t, force=True, ignore_permissions=True)
		cleanup_fiscal_year(getattr(cls, "_created_fy", None))
		super().tearDownClass()

	def _make_ganada(self):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "TAG-" + frappe.generate_hash(length=6),
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cost_center,
				"proposal_title": "TAG " + frappe.generate_hash(length=4),
				"items": [{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}],
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

	def _parent(self, project, phase):
		return frappe.db.get_value(
			"Task", {"project": project, "proposal_phase": phase, "is_group": 1}, "name"
		)

	def test_parent_task_receives_exactly_phase_tags(self):
		q = self._make_ganada()
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])
		project = res["project"]

		parent = self._parent(project, PHASE)
		self.assertTrue(parent)
		self.assertEqual(_tag_links("Task", parent), set(TAGS))
		self.assertEqual(res["parent_tags_applied"], len(TAGS))

		# La fase sin Tags produce Task padre sin Tags.
		parent2 = self._parent(project, PHASE2)
		self.assertTrue(parent2)
		self.assertEqual(_tag_links("Task", parent2), set())

		# La Proposal Phase conserva sus Tags.
		self.assertEqual(_tag_links("Proposal Phase", PHASE), set(TAGS))

	def test_child_tasks_and_other_doctypes_untagged(self):
		q = self._make_ganada()
		res = create_project_from_quotation(q.name)
		self.__class__._projects.append(res["project"])
		project = res["project"]

		children = frappe.get_all("Task", filters={"project": project, "is_group": 0}, pluck="name")
		self.assertTrue(children)
		for c in children:
			self.assertEqual(_tag_links("Task", c), set(), f"Task hija {c} no debe tener Tags")

		# Ningún otro DocType recibe Tags por esta función.
		self.assertEqual(_tag_links("Project", project), set())
		self.assertEqual(_tag_links("Quotation", q.name), set())
		self.assertEqual(_tag_links("Item", ITEM), set())
		for sc in frappe.get_all("Scope Item", filters={"code": ["like", "_TAG_%"]}, pluck="name"):
			self.assertEqual(_tag_links("Scope Item", sc), set())

	def test_retry_does_not_duplicate_tags(self):
		q = self._make_ganada()
		create_project_from_quotation(q.name)
		res2 = create_project_from_quotation(q.name)  # reintento idempotente
		self.__class__._projects.append(res2["project"])
		parent = self._parent(res2["project"], PHASE)

		# Tag Link: exactamente los Tags esperados, sin duplicados.
		links = frappe.get_all(
			"Tag Link", filters={"document_type": "Task", "document_name": parent}, pluck="tag"
		)
		self.assertEqual(sorted(links), sorted(TAGS))
		# _user_tags denormalizado tampoco duplica.
		ut = frappe.db.get_value("Task", parent, "_user_tags") or ""
		self.assertEqual(sorted(t for t in ut.split(",") if t), sorted(TAGS))
