# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Costo externo de compra de un Item, reutilizando el pricing NATIVO de ERPNext (ADR-0017 + ADR-0024).

Contrato monetario (ADR-0024): un costo externo nunca es un número sin moneda. El resolver devuelve un
``ExternalCost`` con la moneda FUENTE (la de la Buying Price List / los rates nativos), el importe
NORMALIZADO a la **moneda base de la Company** (moneda canónica del análisis económico) y el tipo de
cambio nativo usado. Reglas:

- ``Item.is_purchase_item == 0`` → sin costo externo (``no_purchase``). Un servicio propio no arrastra
  costo externo aunque tenga ``valuation_rate``.
- ``Item.is_purchase_item == 1`` → jerarquía nativa:
    1. **Buying Item Price** vigente (``get_item_price``: maneja UOM y vigencia). La Buying Price List se
       resuelve de forma determinista y GENÉRICA (ver ``_resolve_buying_price``); varias listas aplicables
       sin criterio suficiente → ``ambiguo_price_list`` (no se elige arbitrariamente la primera). El
       ``price_list_rate`` viene en la moneda de la Price List y se **convierte a base** con FX nativo
       ``for_buying`` a la fecha económica. FX faltante → ``sin_tipo_cambio``.
    2. ``Item.last_purchase_rate`` (ya en moneda base de la Company).
    3. ``Item.valuation_rate`` (ya en moneda base; solo significativo para stock items).
    4. ``sin_costo``.

``ExternalCost.amount`` (importe normalizado a base) es ``None`` cuando el estado es irresoluble
(``sin_tipo_cambio`` / ``ambiguo_price_list``): NO se degrada silenciosamente a 0 — el gate de snapshot lo
bloquea al formalizar. ``sin_costo``/``no_purchase`` sí son 0 legítimos.

Sin conocimiento de ninguna app consumidora: la frontera es ``Item + contexto económico → costo``.
"""

from typing import NamedTuple

import frappe
from frappe.utils import flt

from erpnext_proposals.erpnext_proposals.utils.currency import (
	MISSING_FX,
	get_company_currency,
	get_price_list_currency,
	try_convert,
)

# Etiquetas de origen (estables; el snapshot las guarda tal cual).
SRC_NO_PURCHASE = "no_purchase"
SRC_ITEM_PRICE = "buying_item_price"
SRC_LAST_PURCHASE = "last_purchase_rate"
SRC_VALUATION = "valuation_rate"
SRC_NONE = "sin_costo"
SRC_MISSING_FX = MISSING_FX  # "sin_tipo_cambio"
SRC_AMBIGUOUS = "ambiguo_price_list"

# Estados irresolubles: el importe normalizado NO existe (None). Bloquean la formalización.
UNRESOLVED_SOURCES = frozenset({SRC_MISSING_FX, SRC_AMBIGUOUS})


class ExternalCost(NamedTuple):
	"""Resultado del resolver de costo externo. ``amount`` está en ``normalized_currency`` (moneda base de
	la Company) y es ``None`` si el estado es irresoluble."""

	amount: float | None  # normalizado a moneda base; None si irresoluble
	source: str
	source_amount: float | None
	source_currency: str | None
	normalized_currency: str | None  # moneda base de la Company
	exchange_rate: float | None
	exchange_date: object | None


def get_buying_price_list() -> str | None:
	"""Buying Price List configurada por defecto (Buying Settings, nativo). Es el criterio determinista de
	desempate cuando hay varias listas de compra con precio para el mismo Item."""
	return frappe.db.get_single_value("Buying Settings", "buying_price_list")


def _buying_price_lists_with_price(item_code: str) -> list[str]:
	"""Todas las Buying Price Lists (``Price List.buying=1``) que tienen algún Item Price para el Item.
	Se apoya en el flag ``buying`` que ERPNext copia del Price List al Item Price."""
	buying_lists = frappe.get_all("Price List", filters={"buying": 1}, pluck="name")
	if not buying_lists:
		return []
	pls = frappe.get_all(
		"Item Price",
		filters={"item_code": item_code, "price_list": ["in", buying_lists]},
		pluck="price_list",
	)
	# Dedup preservando orden estable (nombres de Price List).
	return sorted({pl for pl in pls if pl})


def _price_from_list(item_code: str, price_list: str, uom: str | None, transaction_date) -> float:
	"""``price_list_rate`` vigente del Item en una Price List concreta, vía resolver NATIVO (respeta UOM y
	vigencia ``valid_from/valid_upto``). 0 si no hay precio aplicable."""
	from erpnext.stock.get_item_details import get_item_price

	rows = get_item_price(
		{"price_list": price_list, "uom": uom, "transaction_date": transaction_date},
		item_code,
		ignore_party=True,
	)
	return flt(rows[0].get("price_list_rate")) if rows else 0.0


def _resolve_buying_price(item_code: str, uom: str | None, transaction_date) -> tuple:
	"""Determina de forma DETERMINISTA y genérica el ``(price_list_rate, price_list)`` de compra aplicable.

	Jerarquía (sin elegir arbitrariamente la primera de varias listas):
	  - Se calculan las Buying Price Lists que realmente tienen precio vigente para el Item (respetando
	    UOM/vigencia con el resolver nativo).
	  - Si la Buying Price List configurada en Buying Settings tiene precio → se usa (desempate nativo).
	  - Si exactamente UNA lista tiene precio → se usa.
	  - Si NINGUNA tiene precio → ``(0, None)`` (se cae a los fallbacks nativos).
	  - Si VARIAS tienen precio y la configurada no está entre ellas (o no hay configurada) → ambigüedad:
	    ``(None, None)`` (el llamador lo marca ``ambiguo_price_list``; nunca se elige la primera).
	"""
	configured = get_buying_price_list()
	hits = []
	for pl in _buying_price_lists_with_price(item_code):
		rate = _price_from_list(item_code, pl, uom, transaction_date)
		if rate:
			hits.append((pl, rate))
	if not hits:
		return 0.0, None
	if configured:
		for pl, rate in hits:
			if pl == configured:
				return rate, pl
	if len(hits) == 1:
		return hits[0][1], hits[0][0]
	# Varias listas con precio y sin criterio determinista para elegir → ambigüedad explícita.
	return None, None


def resolve_external_cost(
	item_code: str, uom: str | None = None, transaction_date=None, company: str | None = None
) -> ExternalCost:
	"""Resolución genérica ÚNICA de costo externo (usada por ``Quotation.items`` y ``required_items``).

	Devuelve un ``ExternalCost`` con el importe NORMALIZADO a la moneda base de la Company. ``company`` es
	necesaria para conocer la moneda base y normalizar; si no se pasa se intenta con la Company por defecto
	del sistema."""
	base_currency = get_company_currency(company)
	if not base_currency:
		default_company = frappe.defaults.get_global_default("company")
		base_currency = get_company_currency(default_company)

	def _result(amount, source, source_amount=None, source_currency=None, rate=None):
		return ExternalCost(
			amount=amount,
			source=source,
			source_amount=source_amount,
			source_currency=source_currency,
			normalized_currency=base_currency,
			exchange_rate=rate,
			exchange_date=transaction_date,
		)

	if not item_code:
		return _result(0.0, SRC_NO_PURCHASE)

	item = frappe.db.get_value(
		"Item",
		item_code,
		["is_purchase_item", "stock_uom", "last_purchase_rate", "valuation_rate"],
		as_dict=True,
	)
	if not item or not item.is_purchase_item:
		return _result(0.0, SRC_NO_PURCHASE)

	# 1) Buying Item Price vigente (con moneda de la lista → normalizado a base con FX nativo).
	rate, price_list = _resolve_buying_price(item_code, uom or item.stock_uom, transaction_date)
	if rate is None:
		# Varias listas aplicables sin criterio → ambigüedad (no se elige arbitrariamente).
		return _result(None, SRC_AMBIGUOUS)
	if rate:
		src_currency = get_price_list_currency(price_list) or base_currency
		normalized, fx = try_convert(rate, src_currency, base_currency, transaction_date, for_buying=True)
		if normalized is None:
			# Costo en otra moneda pero sin tipo de cambio → fail-closed (nunca tasa 1).
			return _result(None, SRC_MISSING_FX, source_amount=flt(rate), source_currency=src_currency)
		return _result(
			flt(normalized), SRC_ITEM_PRICE, source_amount=flt(rate), source_currency=src_currency, rate=fx
		)

	# 2) Último precio de compra (nativo: en moneda base de la Company).
	if flt(item.last_purchase_rate):
		return _result(
			flt(item.last_purchase_rate),
			SRC_LAST_PURCHASE,
			source_amount=flt(item.last_purchase_rate),
			source_currency=base_currency,
			rate=1.0,
		)

	# 3) Valuation rate (moneda base; solo significativo para stock items).
	if flt(item.valuation_rate):
		return _result(
			flt(item.valuation_rate),
			SRC_VALUATION,
			source_amount=flt(item.valuation_rate),
			source_currency=base_currency,
			rate=1.0,
		)

	return _result(0.0, SRC_NONE)
