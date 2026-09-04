# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tema 3 (definitivo) — color de Proposal Phase + rango de fase/Project autocalculado.

`Proposal Phase.color` se congela (snapshot) en `Task.color` de la Task padre (`is_group`); las hijas no lo
heredan. La **duración de fase NO se captura**: la ventana de la fase = envelope real de sus Tasks hijas
(min inicio / max fin). El Project obtiene `expected_end_date` = fin más tardío del plan. Datos ficticios
`_T3PD-*`."""

import unittest

import frappe
from frappe.utils import add_days, getdate

from erpnext_proposals.erpnext_proposals.tests.company import get_test_company, get_test_item_group
from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils.project import create_project_from_quotation

PH1, PH2, PHP = "_T3PD_PH1", "_T3PD_PH2", "_T3PD_PHP"
COLOR1, COLOR2 = "#ff0000", "#00ff00"


class TestPhaseColorRange(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._quotations = []
		cls._projects = []
		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company on test site — run bench migrate first.")
		cls._fy = ensure_current_fiscal_year()
		cls.ig = get_test_item_group()
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or frappe.db.get_value(
			"Territory", {}, "name"
		)
		if not cg:
			raise unittest.SkipTest("No Customer Group on test site.")
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		if not frappe.db.exists("Customer", "_T3PD Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_T3PD Customer",
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_T3PD Customer"
		cls.cost_center = frappe.db.get_value(
			"Cost Center", {"is_group": 0, "company": cls.company}, "name"
		) or frappe.db.get_value("Cost Center", {"is_group": 0}, "name")
		if not frappe.db.exists("Proposal Template", "_T3PD Template"):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": "_T3PD Template", "description": "T"}
			).insert(ignore_permissions=True)
		cls._phase(PH1, 10, COLOR1)
		cls._phase(PH2, 20, COLOR2)
		cls._phase(PHP, 30, None)
		# IMAIN: PH1 con 2 hijas (off 0/dur4, off 2/dur3) + PH2 con 1 hija (off 12/dur5).
		cls._item_scope("_T3PD-IMAIN", [("MS1", PH1, "0", 4), ("MS2", PH1, "2", 3), ("MS3", PH2, "12", 5)])
		cls._item_scope("_T3PD-INOCLR", [("NC", PHP, "0", 3)])  # fase sin color
		cls._item_scope("_T3PD-INODAT", [("U1", PH1, "", 3)])  # hija sin offset → no fechable

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
		for code in frappe.get_all("Scope Item", filters={"code": ["like", "_T3PD-%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", code, force=True, ignore_permissions=True)
		for ph in (PH1, PH2, PHP):
			if frappe.db.exists("Proposal Phase", {"phase_code": ph}):
				frappe.delete_doc("Proposal Phase", ph, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", "_T3PD Template"):
			frappe.delete_doc("Proposal Template", "_T3PD Template", force=True, ignore_permissions=True)
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		frappe.db.commit()  # nosemgrep — limpieza de fixtures de test
		super().tearDownClass()

	@classmethod
	def _phase(cls, code, seq, color):
		if frappe.db.exists("Proposal Phase", {"phase_code": code}):
			frappe.delete_doc("Proposal Phase", code, force=True, ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Proposal Phase",
				"phase_code": code,
				"phase_name": code,
				"sequence": seq,
				"enabled": 1,
				"color": color,
			}
		).insert(ignore_permissions=True)

	@classmethod
	def _item_scope(cls, item, scopes):
		if not frappe.db.exists("Item", item):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": item,
					"item_name": item,
					"item_group": cls.ig,
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"is_sales_item": 1,
					"is_purchase_item": 0,
				}
			).insert(ignore_permissions=True)
		for code, phase, off, dur in scopes:
			full = "_T3PD-" + code
			if frappe.db.exists("Scope Item", full):
				frappe.delete_doc("Scope Item", full, force=True, ignore_permissions=True)
			sc = frappe.get_doc(
				{
					"doctype": "Scope Item",
					"code": full,
					"title": full,
					"sequence": 10,
					"enabled": 1,
					"visible_in_proposal": 1,
					"phase": phase,
					"estimated_hours": 4,
					"planned_start_offset_days": off,
					"planned_duration_days": dur,
				}
			)
			sc.append("erpnext_items", {"item": item})
			sc.insert(ignore_permissions=True)

	def _project(self, item):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "T3PD-" + frappe.generate_hash(length=6),
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_template": "_T3PD Template",
				"proposal_cost_center": self.cost_center,
				"proposal_title": "T3PD " + frappe.generate_hash(length=4),
				"items": [{"item_code": item, "item_name": item, "qty": 1, "rate": 1000, "uom": "Nos"}],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._quotations.append(doc.name)
		doc.reload()
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		frappe.db.set_value("Quotation", doc.name, "workflow_state", "Ganada", update_modified=False)
		res = create_project_from_quotation(doc.name)
		self.__class__._projects.append(res["project"])
		return doc.name, res

	def _parent(self, project, phase):
		return frappe.db.get_value(
			"Task",
			{"project": project, "proposal_phase": phase, "is_group": 1},
			["name", "color", "exp_start_date", "exp_end_date"],
			as_dict=True,
		)

	def _pdates(self, project):
		v = frappe.db.get_value(
			"Project", project, ["expected_start_date", "expected_end_date"], as_dict=True
		)
		return getdate(v.expected_start_date), (getdate(v.expected_end_date) if v.expected_end_date else None)

	# ── COLOR ──────────────────────────────────────────────────────────────
	def test_1_parent_gets_phase_color(self):
		_, res = self._project("_T3PD-IMAIN")
		self.assertEqual(self._parent(res["project"], PH1).color, COLOR1)
		self.assertEqual(self._parent(res["project"], PH2).color, COLOR2)

	def test_2_children_do_not_inherit_color(self):
		_, res = self._project("_T3PD-IMAIN")
		children = frappe.get_all(
			"Task", filters={"project": res["project"], "is_group": 0}, fields=["color"]
		)
		self.assertTrue(children)
		self.assertTrue(all(not c.color for c in children))

	def test_3_no_color_no_error(self):
		_, res = self._project("_T3PD-INOCLR")
		self.assertFalse(self._parent(res["project"], PHP).color)

	def test_4_color_is_snapshot_not_retroactive(self):
		_, res = self._project("_T3PD-IMAIN")
		self.assertEqual(self._parent(res["project"], PH1).color, COLOR1)
		frappe.db.set_value("Proposal Phase", PH1, "color", "#123456")
		create_project_from_quotation(
			frappe.db.get_value("Quotation", {"proposal_project": res["project"]}, "name")
		)
		self.assertEqual(self._parent(res["project"], PH1).color, COLOR1)

	# ── RANGO DE FASE / PROJECT ─────────────────────────────────────────────
	def test_5_phase_range_is_min_max_of_children(self):
		# PH1: MS1 (off0 dur4 → +0..+3), MS2 (off2 dur3 → +2..+4) → inicio +0, fin +4.
		_, res = self._project("_T3PD-IMAIN")
		start = getdate(frappe.db.get_value("Project", res["project"], "expected_start_date"))
		p = self._parent(res["project"], PH1)
		self.assertEqual(getdate(p.exp_start_date), start)
		self.assertEqual(getdate(p.exp_end_date), add_days(start, 4))

	def test_6_planned_duration_field_removed(self):
		self.assertIsNone(frappe.get_meta("Proposal Phase").get_field("planned_duration_days"))

	def test_7_phase_without_dated_children_has_no_dates(self):
		_, res = self._project("_T3PD-INODAT")
		p = self._parent(res["project"], PH1)
		self.assertIsNone(p.exp_start_date)  # no se inventan fechas
		self.assertIsNone(p.exp_end_date)

	def test_8_each_phase_reflects_its_children(self):
		_, res = self._project("_T3PD-IMAIN")
		start = getdate(frappe.db.get_value("Project", res["project"], "expected_start_date"))
		p2 = self._parent(res["project"], PH2)  # MS3: off12 dur5 → +12..+16
		self.assertEqual(getdate(p2.exp_start_date), add_days(start, 12))
		self.assertEqual(getdate(p2.exp_end_date), add_days(start, 16))

	def test_9_project_start_contains_plan(self):
		_, res = self._project("_T3PD-IMAIN")
		pstart, _pend = self._pdates(res["project"])
		child_starts = [
			getdate(d)
			for d in frappe.get_all(
				"Task",
				filters={"project": res["project"], "is_group": 0},
				pluck="exp_start_date",
			)
			if d
		]
		self.assertLessEqual(pstart, min(child_starts))  # el inicio del Project no es posterior al plan

	def test_10_project_end_contains_plan(self):
		_, res = self._project("_T3PD-IMAIN")
		start = getdate(frappe.db.get_value("Project", res["project"], "expected_start_date"))
		_pstart, pend = self._pdates(res["project"])
		self.assertEqual(pend, add_days(start, 16))  # fin más tardío del plan (MS3)

	def test_11_child_offsets_preserved(self):
		_, res = self._project("_T3PD-IMAIN")
		start = getdate(frappe.db.get_value("Project", res["project"], "expected_start_date"))
		ms3 = frappe.db.get_value(
			"Task",
			{"project": res["project"], "subject": ["like", "%MS3%"]},
			["exp_start_date", "exp_end_date"],
			as_dict=True,
		)
		self.assertEqual(getdate(ms3.exp_start_date), add_days(start, 12))
		self.assertEqual(getdate(ms3.exp_end_date), add_days(start, 16))

	def test_12_idempotent(self):
		qn, res1 = self._project("_T3PD-IMAIN")
		res2 = create_project_from_quotation(qn)
		self.assertEqual(res2["project"], res1["project"])
		self.assertEqual(res2["tasks_created"], 0)
		self.assertEqual(self._parent(res1["project"], PH1).color, COLOR1)


if __name__ == "__main__":
	unittest.main()
