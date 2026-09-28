# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""UX del PDF "Rentabilidad Estimada": trazabilidad de la fuente del costo externo, distinción entre
costo $0 VÁLIDO (Buying Item Price = 0) y ``sin_costo`` (sin fuente), warnings por línea, y terminología
(Mano de obra interna). El motor económico NO cambia; se verifica solo la PRESENTACIÓN (render del PF).

Datos ficticios; sin conocimiento de apps consumidoras. Company base = MXN.
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

OLD = "2000-01-01"
BPL = "_RUX Buying PL"
TMPL = "_RUX Template"
ACT = "_RUX Activity"
IT_BUY = "_RUX Buy 300"  # vendido comprable, Item Price 300 → buying_item_price
IT_ZERO = "_RUX Buy 0"  # vendido comprable, Item Price 0 → buying_item_price, costo $0 VÁLIDO
IT_NONE = "_RUX No Cost"  # vendido comprable, SIN precio ni last/valuation → sin_costo
IT_SVC = "_RUX Servicio"  # vendido NO comprable → MO por Scope
IT_REQ = "_RUX Req 150"  # requerido comprable, Item Price 150


def _item(code, purchase):
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": get_test_item_group(),
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"is_sales_item": 1,
				"is_purchase_item": 1 if purchase else 0,
			}
		).insert(ignore_permissions=True)


def _price(item, rate):
	name = frappe.db.exists("Item Price", {"item_code": item, "price_list": BPL})
	if name:
		frappe.db.set_value("Item Price", name, {"price_list_rate": rate, "valid_from": OLD})
	else:
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item,
				"price_list": BPL,
				"price_list_rate": rate,
				"valid_from": OLD,
			}
		).insert(ignore_permissions=True)


class TestRentabilidadUX(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()  # MXN
		cls._fy = ensure_current_fiscal_year()
		cls.cc = get_test_cost_center(cls.company)
		cls.pl = get_test_price_list()
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or frappe.db.get_value(
			"Territory", {}, "name"
		)
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		if not frappe.db.exists("Customer", "_RUX Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_RUX Customer",
					"customer_type": "Company",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_RUX Customer"
		if not frappe.db.exists("Activity Type", ACT):
			frappe.get_doc({"doctype": "Activity Type", "activity_type": ACT}).insert(ignore_permissions=True)
		frappe.db.set_value("Activity Type", ACT, "costing_rate", 100)
		if not frappe.db.exists("Proposal Template", TMPL):
			frappe.get_doc({"doctype": "Proposal Template", "template_name": TMPL}).insert(
				ignore_permissions=True
			)
		if not frappe.db.exists("Scope Item", "_RUX SC"):
			frappe.get_doc(
				{"doctype": "Scope Item", "code": "_RUX SC", "title": "Configuración interna", "enabled": 1}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Price List", BPL):
			frappe.get_doc(
				{"doctype": "Price List", "price_list_name": BPL, "buying": 1, "selling": 0, "currency": "MXN"}
			).insert(ignore_permissions=True)
		cls._prev_bpl = frappe.db.get_single_value("Buying Settings", "buying_price_list")
		frappe.db.set_single_value("Buying Settings", "buying_price_list", BPL)
		for c, purchase in [
			(IT_BUY, True),
			(IT_ZERO, True),
			(IT_NONE, True),
			(IT_SVC, False),
			(IT_REQ, True),
		]:
			_item(c, purchase)
		_price(IT_BUY, 300)
		_price(IT_ZERO, 0)
		_price(IT_REQ, 150)
		# IT_NONE: deliberadamente sin Item Price ni last_purchase/valuation → sin_costo.
		cls._quotations = []
		frappe.db.commit()  # nosemgrep — fixtures de test

	@classmethod
	def tearDownClass(cls):
		for n in cls._quotations:
			if frappe.db.exists("Quotation", n):
				try:
					frappe.delete_doc("Quotation", n, force=True, ignore_permissions=True)
				except Exception:
					pass
		frappe.db.set_single_value("Buying Settings", "buying_price_list", cls._prev_bpl or "")
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		frappe.db.commit()  # nosemgrep — limpieza de test
		super().tearDownClass()

	def _make(self, sold, required=None, labor_for=None):
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "RUX-" + frappe.generate_hash(length=8),
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"workflow_state": "Borrador",
				"proposal_template": TMPL,
				"proposal_cost_center": self.cc,
				"selling_price_list": self.pl,
				"items": [{"item_code": c, "item_name": c, "qty": 1, "rate": 1000, "uom": "Nos"} for c in sold],
				"required_items": [{"item": it, "qty": 1, "uom": "Nos"} for it in (required or [])],
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		if labor_for:
			doc = frappe.get_doc("Quotation", doc.name)
			doc.append(
				"quotation_scope_items",
				{
					"scope_item": "_RUX SC",
					"code": "_RUX SC",
					"title": "Configuración interna",
					"item_code": labor_for,
					"activity_type": ACT,
					"designation": "",
					"include_in_proposal": 1,
					"estimated_hours": 10,
					"costing_rate": 100,
					"rate_source": "matrix",
					"planned_start_offset_days": "0",
					"planned_duration_days": 0,
				},
			)
			doc.save(ignore_permissions=True)
		self.__class__._quotations.append(doc.name)
		return doc

	def _html(self, doc):
		return frappe.get_print("Quotation", doc.name, print_format="Rentabilidad Estimada", no_letterhead=1)

	# 1) Buying Item Price normal → muestra costo + fuente "precio de compra"
	def test_buying_price_source_shown(self):
		html = self._html(self._make([IT_BUY]))
		self.assertIn("precio de compra", html)
		self.assertNotIn("sin costo (no encontrado)", html)
		self.assertNotIn("Líneas con costo externo no determinado", html)

	# 2) Buying Item Price = 0 → $0 válido con fuente; NO sin_costo, NO warning falso
	def test_zero_is_valid_not_sin_costo(self):
		html = self._html(self._make([IT_ZERO]))
		self.assertIn("precio de compra", html)
		self.assertNotIn("sin costo (no encontrado)", html)
		self.assertNotIn("Líneas con costo externo no determinado", html)

	# 3) Sin costo encontrado → etiqueta explícita + warning con la línea afectada
	def test_sin_costo_flagged(self):
		html = self._html(self._make([IT_NONE]))
		self.assertIn("sin costo (no encontrado)", html)
		self.assertIn("Líneas con costo externo no determinado", html)
		self.assertIn(IT_NONE, html)

	# 4) MO interna: terminología "Mano de obra interna"
	def test_labor_label(self):
		html = self._html(self._make([IT_SVC], labor_for=IT_SVC))
		self.assertIn("Mano de obra interna", html)

	# 5) Required Item: fuente del costo mostrada, sin inventar clasificación de subcontratación
	def test_required_item_source_shown(self):
		html = self._html(self._make([IT_SVC], required=[IT_REQ], labor_for=IT_SVC))
		self.assertIn("Costos requeridos no asignados", html)
		self.assertIn("precio de compra", html)
		self.assertNotIn("Subcontratación", html)  # no se etiqueta automáticamente

	# 6) Caso mixto: MO + Required externo; el motor no cambia (margen = ingreso - (external+labor))
	def test_mixed_engine_unchanged(self):
		from erpnext_proposals.erpnext_proposals.utils.economic_calendar import get_economic_evaluation

		doc = self._make([IT_SVC], required=[IT_REQ], labor_for=IT_SVC)
		ev = get_economic_evaluation(doc.name)
		t = ev["totals"]
		self.assertAlmostEqual(t["total_cost"], t["external"] + t["labor"], places=2)
		self.assertAlmostEqual(t["margin"], t["revenue"] - t["total_cost"], places=2)
		self.assertGreater(t["labor"], 0)  # MO interna del Scope
		self.assertGreater(t["external"], 0)  # costo del Required Item
