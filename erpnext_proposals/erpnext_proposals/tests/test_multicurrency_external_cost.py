# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0024: costo externo multimoneda genérico.

Verifica la fundación monetaria (``utils.currency``) y el resolver (``utils.item_cost``):
- normalización a moneda base con FX NATIVO de ERPNext (Currency Exchange);
- trazabilidad del origen (importe + moneda origen + FX);
- fail-closed sin tipo de cambio (``sin_tipo_cambio``); nunca 1.0 implícito;
- ambigüedad de Buying Price Lists (``ambiguo_price_list``);
- compatibilidad: misma moneda (MXN/MXN) idéntica al comportamiento previo;
- fallbacks nativos (last_purchase_rate / valuation_rate en moneda base) y ``sin_costo``.

Datos ficticios; sin conocimiento de ninguna app consumidora. Company base = MXN (``get_test_company``).
"""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.company import get_test_company, get_test_item_group
from erpnext_proposals.erpnext_proposals.utils.currency import (
	MissingExchangeRate,
	convert,
	try_convert,
)
from erpnext_proposals.erpnext_proposals.utils.item_cost import get_buying_price_list, resolve_external_cost

DATE = "2026-09-23"
OLD = "2000-01-01"  # fecha de la tasa (<= DATE) para que get_exchange_rate la encuentre

BUY_MXN = "_Test Buy MXN"
BUY_USD = "_Test Buy USD"
BUY_EUR = "_Test Buy EUR"


def _price_list(name, currency):
	if not frappe.db.exists("Price List", name):
		frappe.get_doc(
			{"doctype": "Price List", "price_list_name": name, "buying": 1, "currency": currency}
		).insert(ignore_permissions=True)


def _fx(frm, to, rate):
	if not frappe.db.exists("Currency Exchange", {"from_currency": frm, "to_currency": to, "date": OLD}):
		frappe.get_doc(
			{
				"doctype": "Currency Exchange",
				"date": OLD,
				"from_currency": frm,
				"to_currency": to,
				"exchange_rate": rate,
				"for_buying": 1,
				"for_selling": 1,
			}
		).insert(ignore_permissions=True)


def _item(code, is_purchase=1, lpr=0.0, vr=0.0):
	if not frappe.db.exists("UOM", "Nos"):
		frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": get_test_item_group(),
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"is_purchase_item": is_purchase,
				"last_purchase_rate": lpr,
				"valuation_rate": vr,
			}
		).insert(ignore_permissions=True)
	return code


def _item_price(item, price_list, rate):
	# valid_from explícito y antiguo: Frappe auto-asigna valid_from=hoy si se omite, y get_item_price filtra
	# por vigencia contra transaction_date (DATE). Con OLD el precio es vigente en la fecha de la prueba.
	# Upsert idempotente (los tests que commitean en setUpClass pueden dejar datos persistidos entre corridas).
	name = frappe.db.exists("Item Price", {"item_code": item, "price_list": price_list})
	if name:
		frappe.db.set_value("Item Price", name, {"price_list_rate": rate, "valid_from": OLD})
	else:
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item,
				"price_list": price_list,
				"price_list_rate": rate,
				"valid_from": OLD,
			}
		).insert(ignore_permissions=True)


class TestMulticurrencyExternalCost(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()  # MXN
		# HERMETICIDAD FX: deshabilitar el servicio de tipo de cambio (API externa) para que
		# get_exchange_rate consulte SOLO los Currency Exchange que sembramos y devuelva 0 cuando falten
		# (fail-closed). Sin esto, un runner con la API habilitada (p. ej. CI) resuelve tasas reales y los
		# casos "falta FX" no se reproducen. Se restaura en tearDownClass.
		cls._prev_fx_disabled = frappe.db.get_single_value("Currency Exchange Settings", "disabled")
		frappe.db.set_single_value("Currency Exchange Settings", "disabled", 1)
		_price_list(BUY_MXN, "MXN")
		_price_list(BUY_USD, "USD")
		_price_list(BUY_EUR, "EUR")
		_fx("USD", "MXN", 18.0)  # para normalizar USD→MXN (base)
		_fx("USD", "EUR", 0.9)  # para consultas en moneda objetivo (target_currency)
		cls._prev_buying = get_buying_price_list()
		frappe.db.commit()  # nosemgrep — fixtures de test

	@classmethod
	def tearDownClass(cls):
		frappe.db.set_single_value("Buying Settings", "buying_price_list", cls._prev_buying or "")
		frappe.db.set_single_value("Currency Exchange Settings", "disabled", cls._prev_fx_disabled or 0)
		frappe.db.commit()  # nosemgrep — limpieza de test
		super().tearDownClass()

	def _set_buying(self, price_list):
		frappe.db.set_single_value("Buying Settings", "buying_price_list", price_list)

	# ── Fundación monetaria (utils.currency) ────────────────────────────────
	def test_convert_same_currency_is_identity(self):
		self.assertEqual(try_convert(100, "MXN", "MXN", DATE), (100.0, 1.0))
		self.assertEqual(convert(100, "MXN", "MXN", DATE), (100.0, 1.0))

	def test_convert_with_native_fx(self):
		amt, rate = convert(10, "USD", "MXN", DATE, for_buying=True)
		self.assertEqual((amt, rate), (180.0, 18.0))

	def test_missing_fx_try_convert_is_none(self):
		# EUR→MXN no tiene Currency Exchange → nunca 1.0.
		self.assertEqual(try_convert(5, "EUR", "MXN", DATE), (None, None))

	def test_missing_fx_convert_raises(self):
		with self.assertRaises(MissingExchangeRate):
			convert(5, "EUR", "MXN", DATE)

	# ── Caso A: misma moneda (compat idéntica) ──────────────────────────────
	def test_A_same_currency_mxn(self):
		self._set_buying(BUY_MXN)
		it = _item("_Test MC A")
		_item_price(it, BUY_MXN, 100)
		ec = resolve_external_cost(it, uom="Nos", transaction_date=DATE, company=self.company)
		self.assertEqual((ec.amount, ec.source), (100.0, "buying_item_price"))
		self.assertEqual((ec.source_amount, ec.source_currency, ec.exchange_rate), (100.0, "MXN", 1.0))
		self.assertEqual(ec.normalized_currency, "MXN")

	# ── Caso B: costo USD normalizado a base MXN con FX ─────────────────────
	def test_B_usd_cost_normalized_to_base(self):
		self._set_buying(BUY_USD)
		it = _item("_Test MC B")
		_item_price(it, BUY_USD, 10)
		ec = resolve_external_cost(it, uom="Nos", transaction_date=DATE, company=self.company)
		self.assertEqual((ec.amount, ec.source), (180.0, "buying_item_price"))
		# Trazabilidad del origen: importe original + moneda origen + FX (no queda como "180" pelón).
		self.assertEqual((ec.source_amount, ec.source_currency, ec.exchange_rate), (10.0, "USD", 18.0))
		self.assertEqual(ec.normalized_currency, "MXN")

	# ── Caso E: math base distinta (MXN→USD) vía FX nativo ──────────────────
	def test_E_base_currency_conversion_math(self):
		# base USD, costo en MXN: convert(180 MXN → USD) con FX MXN→USD = 1/18.
		_fx("MXN", "USD", 1.0 / 18.0)
		amt, _rate = convert(180, "MXN", "USD", DATE, for_buying=True)
		self.assertAlmostEqual(amt, 10.0, places=4)

	# ── Caso F: costo en otra moneda pero SIN FX → fail-closed ──────────────
	def test_F_missing_fx_is_sin_tipo_cambio(self):
		self._set_buying(BUY_EUR)
		it = _item("_Test MC F")
		_item_price(it, BUY_EUR, 5)  # EUR sin Currency Exchange → irresoluble
		ec = resolve_external_cost(it, uom="Nos", transaction_date=DATE, company=self.company)
		self.assertEqual(ec.source, "sin_tipo_cambio")
		self.assertIsNone(ec.amount)  # nunca se degrada a 0 ni a tasa 1
		self.assertEqual((ec.source_amount, ec.source_currency), (5.0, "EUR"))

	# ── Caso G: dos Buying Price Lists aplicables sin criterio → ambigüedad ──
	def test_G_ambiguous_price_lists(self):
		it = _item("_Test MC G")
		_item_price(it, BUY_MXN, 100)
		_item_price(it, BUY_USD, 10)
		# Buying Settings apunta a una lista SIN precio para el item → no desempata → ambiguo.
		self._set_buying(BUY_EUR)
		ec = resolve_external_cost(it, uom="Nos", transaction_date=DATE, company=self.company)
		self.assertEqual(ec.source, "ambiguo_price_list")
		self.assertIsNone(ec.amount)

	def test_G_configured_list_disambiguates(self):
		# Item con 2 listas de compra; la configurada SÍ tiene precio → desempata (determinista, no ambiguo).
		it = _item("_Test MC G2")
		_item_price(it, BUY_MXN, 100)
		_item_price(it, BUY_USD, 10)
		self._set_buying(BUY_MXN)
		ec = resolve_external_cost(it, uom="Nos", transaction_date=DATE, company=self.company)
		self.assertEqual((ec.amount, ec.source, ec.source_currency), (100.0, "buying_item_price", "MXN"))

	# ── Caso H: fallbacks nativos (moneda base) y sin_costo/no_purchase ─────
	def test_H_fallback_last_purchase_is_base(self):
		self._set_buying(BUY_MXN)
		it = _item("_Test MC H LPR", lpr=250)
		ec = resolve_external_cost(it, uom="Nos", transaction_date=DATE, company=self.company)
		self.assertEqual((ec.amount, ec.source, ec.source_currency), (250.0, "last_purchase_rate", "MXN"))

	def test_H_sin_costo_and_no_purchase(self):
		self._set_buying(BUY_MXN)
		it = _item("_Test MC H NONE")
		ec = resolve_external_cost(it, uom="Nos", transaction_date=DATE, company=self.company)
		self.assertEqual((ec.amount, ec.source), (0.0, "sin_costo"))
		nop = _item("_Test MC H NOPUR", is_purchase=0)
		ec = resolve_external_cost(nop, uom="Nos", transaction_date=DATE, company=self.company)
		self.assertEqual((ec.amount, ec.source), (0.0, "no_purchase"))

	# ── target_currency: consulta del costo en una moneda objetivo (ADR-0024) ───
	def _usd_item(self):
		"""Item comprable con Buying Item Price de 10 USD (Buying Settings → BUY_USD)."""
		self._set_buying(BUY_USD)
		it = _item("_Test MC TGT")
		_item_price(it, BUY_USD, 10)
		return it

	def test_target_A_same_as_source_no_fx(self):
		# Source USD 10, target USD → USD 10 (rate 1, sin FX). Economics (amount base) intacto en paralelo.
		it = self._usd_item()
		ec = resolve_external_cost(
			it, uom="Nos", transaction_date=DATE, company=self.company, target_currency="USD"
		)
		self.assertEqual((ec.amount, ec.normalized_currency, ec.exchange_rate), (10.0, "USD", 1.0))
		self.assertEqual(
			(ec.source_amount, ec.source_currency, ec.source), (10.0, "USD", "buying_item_price")
		)

	def test_target_B_to_base_mxn(self):
		# Source USD 10, target MXN (base), FX 18 → MXN 180 (mismo resultado que economics).
		it = self._usd_item()
		ec = resolve_external_cost(
			it, uom="Nos", transaction_date=DATE, company=self.company, target_currency="MXN"
		)
		self.assertEqual((ec.amount, ec.normalized_currency, ec.exchange_rate), (180.0, "MXN", 18.0))

	def test_target_C_to_third_currency_direct_fx(self):
		# Source USD 10, target EUR → FX DIRECTO USD→EUR (0.9), NUNCA USD→MXN→EUR. → EUR 9.
		it = self._usd_item()
		ec = resolve_external_cost(
			it, uom="Nos", transaction_date=DATE, company=self.company, target_currency="EUR"
		)
		self.assertEqual((ec.amount, ec.normalized_currency, ec.exchange_rate), (9.0, "EUR", 0.9))
		self.assertEqual((ec.source_amount, ec.source_currency), (10.0, "USD"))

	def test_target_D_without_target_is_base_unchanged(self):
		# Sin target_currency → comportamiento actual idéntico (normaliza a base MXN).
		it = self._usd_item()
		ec = resolve_external_cost(it, uom="Nos", transaction_date=DATE, company=self.company)
		self.assertEqual((ec.amount, ec.normalized_currency, ec.exchange_rate), (180.0, "MXN", 18.0))

	def test_target_E_missing_fx_is_sin_tipo_cambio(self):
		# Source USD, target GBP sin Currency Exchange USD→GBP → sin_tipo_cambio (nunca tasa 1).
		it = self._usd_item()
		ec = resolve_external_cost(
			it, uom="Nos", transaction_date=DATE, company=self.company, target_currency="GBP"
		)
		self.assertEqual(ec.source, "sin_tipo_cambio")
		self.assertIsNone(ec.amount)
		self.assertEqual((ec.source_amount, ec.source_currency), (10.0, "USD"))
