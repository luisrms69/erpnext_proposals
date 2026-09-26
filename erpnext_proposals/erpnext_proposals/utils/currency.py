# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Fundación monetaria genérica: conversión FX reutilizando el mecanismo NATIVO de ERPNext v16 (ADR-0024).

Principios (genéricos; sin conocimiento de ninguna app consumidora):

- **Moneda canónica del análisis económico interno = ``Company.default_currency`` (base).** Todo importe
  externo se normaliza a base antes de sumar/comparar/calcular margen. La presentación al usuario en la
  moneda de la Quotation se deriva después con el ``conversion_rate`` NATIVO de la Quotation.
- **Contrato monetario:** ningún importe se trata como número sin moneda. Un monto viaja con su moneda y
  su fecha económica; convertir es explícito y por fecha.
- **FX exclusivamente nativo:** ``erpnext.setup.utils.get_exchange_rate`` (consulta ``Currency Exchange``).
  No se crea DocType FX propio, ni tabla paralela, ni tasas hardcodeadas.
- **Nunca asumir 1.0 cuando falta tasa.** ``get_exchange_rate`` devuelve ``0`` si no hay tasa; eso es
  fail-closed explícito: ``convert`` lanza ``MissingExchangeRate`` y ``try_convert`` devuelve ``None``.
"""

import frappe
from frappe import _
from frappe.utils import flt

# Etiqueta estable de FX faltante (se propaga como ``source`` en el resolver de costo externo).
MISSING_FX = "sin_tipo_cambio"


class MissingExchangeRate(frappe.ValidationError):
	"""No existe tipo de cambio nativo para (from_currency → to_currency) en/antes de la fecha dada."""


def get_company_currency(company: str | None) -> str | None:
	"""Moneda base de la Company (fuente nativa; caché de metadata)."""
	if not company:
		return None
	return frappe.get_cached_value("Company", company, "default_currency")


def get_price_list_currency(price_list: str | None) -> str | None:
	"""Moneda de una Price List (fuente nativa)."""
	if not price_list:
		return None
	return frappe.get_cached_value("Price List", price_list, "currency")


def get_native_exchange_rate(
	from_currency: str, to_currency: str, date=None, for_buying: bool = False, for_selling: bool = False
) -> float:
	"""Tasa NATIVA ``from_currency → to_currency`` a la fecha dada. Devuelve ``0.0`` si no hay tasa (nunca
	inventa 1.0). Misma moneda → ``1.0`` sin consultar. ``for_buying``/``for_selling`` filtran la dirección
	de la tasa en ``Currency Exchange`` (nativo)."""
	if not from_currency or not to_currency:
		return 0.0
	if from_currency == to_currency:
		return 1.0
	from erpnext.setup.utils import get_exchange_rate

	args = "for_buying" if for_buying else ("for_selling" if for_selling else None)
	return flt(get_exchange_rate(from_currency, to_currency, date, args))


def try_convert(
	amount,
	from_currency: str | None,
	to_currency: str | None,
	date=None,
	for_buying: bool = False,
	for_selling: bool = False,
) -> tuple[float | None, float | None]:
	"""Convierte ``amount`` de ``from_currency`` a ``to_currency`` a la fecha dada usando FX nativo.

	Devuelve ``(converted_amount, exchange_rate)``. Misma moneda (o alguna vacía con la otra igual) → tasa
	``1.0`` sin consultar FX. **FX faltante → ``(None, None)``** (fail-closed silencioso: el llamador decide
	cómo señalarlo; nunca se asume 1.0)."""
	amt = flt(amount)
	if not from_currency or not to_currency or from_currency == to_currency:
		return amt, 1.0
	rate = get_native_exchange_rate(
		from_currency, to_currency, date, for_buying=for_buying, for_selling=for_selling
	)
	if not rate:
		return None, None
	return amt * rate, rate


def convert(
	amount,
	from_currency: str | None,
	to_currency: str | None,
	date=None,
	for_buying: bool = False,
	for_selling: bool = False,
) -> tuple[float, float]:
	"""Como ``try_convert`` pero **fail-closed duro**: si falta la tasa lanza ``MissingExchangeRate``.
	Devuelve ``(converted_amount, exchange_rate)``."""
	converted, rate = try_convert(
		amount, from_currency, to_currency, date, for_buying=for_buying, for_selling=for_selling
	)
	if converted is None:
		frappe.throw(
			_(
				"No hay tipo de cambio nativo {0} → {1} en/antes de {2}. Sin FX no se puede normalizar el importe (fail-closed)."
			).format(from_currency, to_currency, date or _("hoy")),
			exc=MissingExchangeRate,
		)
	return converted, rate
