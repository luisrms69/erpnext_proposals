# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tema 2 — el nombre del Project incluye el Proposal Group al FINAL.

Unitarios puros de `_build_project_name` (todos los casos) + una prueba de integración que confirma el
nombre extremo a extremo y la idempotencia de `create_project_from_quotation`. Datos ficticios `_T2PN-*`."""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.company import get_test_company, get_test_item_group
from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils.project import (
	_PROJECT_NAME_MAXLEN,
	_build_project_name,
	create_project_from_quotation,
)

GROUP = "Proyecto Agile"


class TestBuildProjectName(unittest.TestCase):
	"""Unitarios puros — sin BD."""

	def test_appends_group_at_end(self):
		self.assertEqual(
			_build_project_name("Cliente", "Implementación ERP", GROUP), f"Implementación ERP — {GROUP}"
		)

	def test_no_group_keeps_base(self):
		self.assertEqual(_build_project_name("Cliente", "Implementación ERP", ""), "Implementación ERP")
		self.assertEqual(_build_project_name("Cliente", "Implementación ERP", None), "Implementación ERP")
		# sin group NO deja guion/espacio sobrante ni None
		out = _build_project_name("Cliente", "Implementación ERP", "   ")
		self.assertEqual(out, "Implementación ERP")
		self.assertNotIn("None", out)

	def test_already_suffix_em_dash_not_duplicated(self):
		self.assertEqual(
			_build_project_name("C", f"Implementación ERP — {GROUP}", GROUP), f"Implementación ERP — {GROUP}"
		)

	def test_already_suffix_hyphen_not_duplicated(self):
		# separador con guion normal también se reconoce como sufijo ya presente
		self.assertEqual(
			_build_project_name("C", f"Implementación ERP - {GROUP}", GROUP), f"Implementación ERP - {GROUP}"
		)

	def test_no_aggressive_match(self):
		# "Manage" termina en "age" pero NO como sufijo con separador → se añade (sin falso positivo)
		self.assertEqual(_build_project_name("C", "Manage", "age"), "Manage — age")

	def test_fallback_no_title_uses_customer_and_group(self):
		out = _build_project_name("Cliente X", "", GROUP)
		self.assertEqual(out, f"Cliente X — {GROUP}")
		self.assertTrue(out.endswith(GROUP))

	def test_no_title_no_group(self):
		self.assertEqual(_build_project_name("Cliente X", None, None), "Cliente X")

	def test_group_with_spaces_preserved(self):
		g = "Grupo Con Espacios 123"
		self.assertEqual(_build_project_name("C", "Base", g), f"Base — {g}")

	def test_truncation_keeps_group_at_end(self):
		long_base = "B" * 200  # excede holgadamente 140 con el sufijo
		out = _build_project_name("C", long_base, GROUP)
		self.assertLessEqual(len(out), _PROJECT_NAME_MAXLEN)
		self.assertTrue(out.endswith(GROUP))  # el Proposal Group se conserva completo al final
		self.assertTrue(out.startswith("B"))  # se truncó la base, no el group


class TestProjectNameIntegration(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._quotations = []
		cls._projects = []
		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company on test site — run bench migrate first.")
		cls._fy = ensure_current_fiscal_year()
		ig = get_test_item_group()
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or frappe.db.get_value(
			"Territory", {}, "name"
		)
		if not cg:
			raise unittest.SkipTest("No Customer Group on test site.")
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		if not frappe.db.exists("Customer", "_T2PN Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_T2PN Customer",
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_T2PN Customer"
		cls.cost_center = frappe.db.get_value(
			"Cost Center", {"is_group": 0, "company": cls.company}, "name"
		) or frappe.db.get_value("Cost Center", {"is_group": 0}, "name")
		if not frappe.db.exists("Item", "_T2PN Item"):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "_T2PN Item",
					"item_name": "_T2PN Item",
					"item_group": ig,
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"is_sales_item": 1,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", "_T2PN Template"):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": "_T2PN Template", "description": "T"}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Phase", {"phase_code": "_T2PN_PH"}):
			frappe.get_doc(
				{
					"doctype": "Proposal Phase",
					"phase_code": "_T2PN_PH",
					"phase_name": "_T2PN_PH",
					"sequence": 10,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		if frappe.db.exists("Scope Item", "_T2PN-S1"):
			frappe.delete_doc("Scope Item", "_T2PN-S1", force=True, ignore_permissions=True)
		sc = frappe.get_doc(
			{
				"doctype": "Scope Item",
				"code": "_T2PN-S1",
				"title": "_T2PN-S1",
				"sequence": 10,
				"enabled": 1,
				"visible_in_proposal": 1,
				"phase": "_T2PN_PH",
				"estimated_hours": 4,
			}
		)
		sc.append("erpnext_items", {"item": "_T2PN Item"})
		sc.insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		for name in cls._projects:
			if frappe.db.exists("Project", name):
				for tk in frappe.get_all("Task", filters={"project": name}, pluck="name"):
					frappe.delete_doc("Task", tk, force=True, ignore_permissions=True)
				frappe.delete_doc("Project", name, force=True, ignore_permissions=True)
		for name in cls._quotations:
			if frappe.db.exists("Quotation", name):
				qd = frappe.get_doc("Quotation", name)
				if qd.docstatus == 1:
					qd.flags.ignore_permissions = True
					try:
						qd.cancel()
					except Exception:
						pass
				frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
		if frappe.db.exists("Scope Item", "_T2PN-S1"):
			frappe.delete_doc("Scope Item", "_T2PN-S1", force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", "_T2PN Template"):
			frappe.delete_doc("Proposal Template", "_T2PN Template", force=True, ignore_permissions=True)
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		frappe.db.commit()  # nosemgrep — limpieza de fixtures de test
		super().tearDownClass()

	def _won_quotation(self, title, group):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": group,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_template": "_T2PN Template",
				"proposal_cost_center": self.cost_center,
				"proposal_title": title,
				"items": [
					{
						"item_code": "_T2PN Item",
						"item_name": "_T2PN Item",
						"qty": 1,
						"rate": 1000,
						"uom": "Nos",
					}
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
		return doc.name

	def test_name_ends_with_group_and_idempotent(self):
		group = "T2PN-" + frappe.generate_hash(length=6)
		qn = self._won_quotation("Proyecto Base T2", group)
		res1 = create_project_from_quotation(qn)
		self.__class__._projects.append(res1["project"])
		pname = frappe.db.get_value("Project", res1["project"], "project_name")
		self.assertTrue(pname.endswith(group), f"project_name={pname!r} no termina con {group}")
		self.assertTrue(pname.startswith("Proyecto Base T2"))
		# idempotencia: segundo intento → mismo Project, mismo nombre
		res2 = create_project_from_quotation(qn)
		self.assertEqual(res2["project"], res1["project"])
		self.assertEqual(res2["tasks_created"], 0)
		self.assertEqual(frappe.db.get_value("Project", res2["project"], "project_name"), pname)


if __name__ == "__main__":
	unittest.main()
