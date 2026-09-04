# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tema 3 — color y duración planificada de Proposal Phase.

Al generar el Project, la Task padre de cada fase congela (snapshot) el `color` y la `duration` de la
Proposal Phase en los campos NATIVOS de Task. La duración es un mínimo: la fase se expande para contener sus
hijas pero nunca las recorta ni las mueve. Datos ficticios `_T3PD-*`."""

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


class TestPhaseColorDuration(unittest.TestCase):
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
		# Fases: PH1 (color rojo, dur 10), PH2 (color verde, dur 8), PHP (sin color, sin duración).
		cls._phase(PH1, 10, COLOR1, 10)
		cls._phase(PH2, 20, COLOR2, 8)
		cls._phase(PHP, 30, None, 0)
		# Items + scopes por escenario (cada scope ligado a UN item vía erpnext_items).
		cls._item_scope("_T3PD-IMAIN", [("MS1", PH1, "0", 3, 0), ("MS2", PH2, "5", 2, 0)])
		cls._item_scope("_T3PD-IEXCEED", [("E1", PH2, "0", 20, 0)])
		cls._item_scope("_T3PD-INODUR", [("N1", PHP, "0", 3, 0)])
		cls._item_scope("_T3PD-IUNDAT", [("U1", PH1, "", 3, 0)])  # sin offset → hija no fechable
		cls._item_scope("_T3PD-ISEQ", [("Q1", PH1, "", 3, 0), ("Q2", PH2, "", 3, 0)])

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
	def _phase(cls, code, seq, color, dur):
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
				"planned_duration_days": dur,
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
				}
			).insert(ignore_permissions=True)
		for code, phase, off, dur, ms in scopes:
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
					"is_milestone": ms,
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
			["name", "color", "duration", "exp_start_date", "exp_end_date"],
			as_dict=True,
		)

	def _pstart(self, project):
		return getdate(frappe.db.get_value("Project", project, "expected_start_date"))

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
		self.assertTrue(all(not c.color for c in children))  # ninguna hija recibe color

	def test_3_no_color_no_error(self):
		_, res = self._project("_T3PD-INODUR")
		self.assertFalse(self._parent(res["project"], PHP).color)  # sin color → generación normal

	def test_4_color_is_snapshot_not_retroactive(self):
		_, res = self._project("_T3PD-IMAIN")
		self.assertEqual(self._parent(res["project"], PH1).color, COLOR1)
		# cambiar el color del catálogo DESPUÉS no altera el Project ya creado (ni al re-generar).
		frappe.db.set_value("Proposal Phase", PH1, "color", "#123456")
		create_project_from_quotation(
			frappe.db.get_value("Quotation", {"proposal_project": res["project"]}, "name")
		)
		self.assertEqual(self._parent(res["project"], PH1).color, COLOR1)

	# ── DURACIÓN ────────────────────────────────────────────────────────────
	def test_5_duration_is_minimum_window(self):
		# PH1 dur 10; hija termina en +2 (< 10) → la ventana del padre dura al menos 10 días.
		_, res = self._project("_T3PD-IMAIN")
		p = self._parent(res["project"], PH1)
		start = self._pstart(res["project"])
		self.assertEqual(p.duration, 10)  # snapshot congelado
		self.assertEqual(getdate(p.exp_start_date), start)
		self.assertEqual(getdate(p.exp_end_date), add_days(start, 9))  # start + dur - 1

	def test_6_child_beyond_duration_expands_phase(self):
		# PH2 dur 8; hija dura 20 días → el padre se EXPANDE para contenerla (no la recorta).
		_, res = self._project("_T3PD-IEXCEED")
		p = self._parent(res["project"], PH2)
		start = self._pstart(res["project"])
		self.assertEqual(getdate(p.exp_end_date), add_days(start, 19))  # fin de la hija, no dur-1

	def test_7_no_duration_keeps_rollup(self):
		# PHP sin duración → ventana = min/max de las hijas (comportamiento previo).
		_, res = self._project("_T3PD-INODUR")
		p = self._parent(res["project"], PHP)
		start = self._pstart(res["project"])
		self.assertEqual(p.duration, 0)
		self.assertEqual(getdate(p.exp_start_date), start)
		self.assertEqual(getdate(p.exp_end_date), add_days(start, 2))  # off0 dur3 → +2

	def test_8_phase_without_dated_children_uses_duration(self):
		# Hija no fechable (sin offset) + duración → la fase existe con ventana (inicio secuencial).
		_, res = self._project("_T3PD-IUNDAT")
		p = self._parent(res["project"], PH1)
		start = self._pstart(res["project"])
		self.assertEqual(getdate(p.exp_start_date), start)  # primera fase arranca en el inicio del proyecto
		self.assertEqual(getdate(p.exp_end_date), add_days(start, 9))  # dur 10

	def test_9_sequential_phases_no_overlap(self):
		# Dos fases con hijas no fechables + duración → PH2 arranca tras el fin de PH1 (sin solaparse).
		_, res = self._project("_T3PD-ISEQ")
		start = self._pstart(res["project"])
		p1, p2 = self._parent(res["project"], PH1), self._parent(res["project"], PH2)
		self.assertEqual(getdate(p1.exp_end_date), add_days(start, 9))  # PH1: start..+9 (dur 10)
		self.assertEqual(getdate(p2.exp_start_date), add_days(start, 10))  # PH2 arranca en +10
		self.assertEqual(getdate(p2.exp_end_date), add_days(start, 17))  # +10..+17 (dur 8)

	def test_10_child_offsets_preserved(self):
		# La duración de fase NO altera las fechas de las hijas (offset/dependencias intactos).
		_, res = self._project("_T3PD-IMAIN")
		start = self._pstart(res["project"])
		ms2 = frappe.db.get_value(
			"Task",
			{
				"project": res["project"],
				"source_quotation_scope_item": ["is", "set"],
				"subject": ["like", "%MS2%"],
			},
			["exp_start_date", "exp_end_date"],
			as_dict=True,
		)
		self.assertEqual(getdate(ms2.exp_start_date), add_days(start, 5))  # offset 5 respetado
		self.assertEqual(getdate(ms2.exp_end_date), add_days(start, 6))  # dur 2

	def test_11_idempotent(self):
		qn, res1 = self._project("_T3PD-IMAIN")
		res2 = create_project_from_quotation(qn)
		self.assertEqual(res2["project"], res1["project"])
		self.assertEqual(res2["tasks_created"], 0)
		self.assertEqual(self._parent(res1["project"], PH1).color, COLOR1)  # snapshot intacto


if __name__ == "__main__":
	unittest.main()
