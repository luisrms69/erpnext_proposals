# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Costo externo de compra de un Item, reutilizando el pricing NATIVO de ERPNext (ADR-0017).

Regla:
- ``Item.is_purchase_item == 0`` → costo externo 0 (``no_purchase``). Un servicio propio no arrastra costo
  externo aunque tenga ``valuation_rate`` capturado.
- ``Item.is_purchase_item == 1`` → jerarquía nativa:
    1. Item Price de compra vigente vía ``erpnext.stock.get_item_details.get_item_price`` (maneja UOM,
       vigencia ``valid_from/valid_upto`` y supplier de forma nativa; NO reimplementamos el query).
    2. ``Item.last_purchase_rate``.
    3. ``Item.valuation_rate``.
    4. sin costo.

Supplier Quotation automática queda FUERA (se retomará solo con referencia explícita por línea; ver ADR-0017).

Moneda: se devuelve el rate tal cual del pricing (moneda de la lista de compra). En el setup normal la
lista de compra está en moneda base; el reporte de rentabilidad ya advierte si la Quotation está en otra
moneda. Conversión FX por periodo/lista queda diferida (ADR-0017 §14).
"""

import frappe
from frappe.utils import flt

# Etiquetas de origen (estables; el reporte y el snapshot las guardan tal cual).
SRC_NO_PURCHASE = "no_purchase"
SRC_ITEM_PRICE = "buying_item_price"
SRC_LAST_PURCHASE = "last_purchase_rate"
SRC_VALUATION = "valuation_rate"
SRC_NONE = "sin_costo"


def get_buying_price_list() -> str | None:
	"""Buying Price List determinista desde la configuración NATIVA (Buying Settings)."""
	return frappe.db.get_single_value("Buying Settings", "buying_price_list")


def resolve_external_cost(item_code: str, uom: str | None = None, transaction_date=None) -> tuple[float, str]:
	"""Devuelve ``(rate_por_unidad, source)``. ``rate=0`` con source ``no_purchase`` si el Item no es
	comprable; ``sin_costo`` si es comprable pero no hay ninguna fuente."""
	if not item_code:
		return 0.0, SRC_NO_PURCHASE

	item = frappe.db.get_value(
		"Item",
		item_code,
		["is_purchase_item", "stock_uom", "last_purchase_rate", "valuation_rate"],
		as_dict=True,
	)
	if not item or not item.is_purchase_item:
		return 0.0, SRC_NO_PURCHASE

	# 1) Item Price de compra vigente (resolver nativo).
	price_list = get_buying_price_list()
	if price_list:
		from erpnext.stock.get_item_details import get_item_price

		rows = get_item_price(
			{
				"price_list": price_list,
				"uom": uom or item.stock_uom,
				"transaction_date": transaction_date,
			},
			item_code,
			ignore_party=True,
		)
		if rows and flt(rows[0].get("price_list_rate")):
			return flt(rows[0].get("price_list_rate")), SRC_ITEM_PRICE

	# 2) Último precio de compra.
	if flt(item.last_purchase_rate):
		return flt(item.last_purchase_rate), SRC_LAST_PURCHASE

	# 3) Valuation rate (solo significativo para stock items).
	if flt(item.valuation_rate):
		return flt(item.valuation_rate), SRC_VALUATION

	return 0.0, SRC_NONE
