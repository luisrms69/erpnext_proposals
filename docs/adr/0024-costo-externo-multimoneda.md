# ADR-0024: Costo externo multimoneda — moneda canónica base, FX nativo y presentación en Quotation currency

**Fecha:** 2026-09-26
**Status:** Implementado
**Rama:** feat/multicurrency-external-cost → version-16
**Relacionado:** enmienda [ADR-0017](0017-required-items-modelo-economico-aditivo.md) (§7 freeze en moneda base, §14 "FX diferido") y [ADR-0018](0018-evaluacion-economica-por-periodos.md); consumido por [ADR-0020](0020-contrato-economico-project.md)

---

## 1. Contexto

`resolve_external_cost()` (ADR-0017 §9) resolvía el costo externo de compra con el pricing nativo de
ERPNext (`get_item_price`) tomando una única Buying Price List desde `Buying Settings.buying_price_list`,
y trataba el `price_list_rate` **como un número sin moneda**: lo persistía directo en `frozen_cost_rate`.

En un ERP multimoneda esto es incorrecto:

- El costo de un proveedor puede estar en USD, la moneda base de la Company en MXN, y la propuesta
  presentarse al cliente en MXN, USD o EUR. `Quotation.currency` **no** es necesariamente igual a
  `Company.default_currency` ni a la moneda de la Buying Price List.
- El reporte de Rentabilidad y el Calendario Económico **sumaban directamente** ingreso (en
  `Quotation.currency`), costo externo (en moneda de la lista de compra) y costo laboral (en moneda base,
  derivada de salarios) — una suma entre monedas distintas, con margen inválido.
- Se asumía **una Company = una Buying Price List**; un Item puede tener costo en varias listas (MXN, USD,
  EUR).
- El contrato económico del Project (ADR-0020) **bloqueaba** cualquier propuesta con `currency ≠ base` o
  `conversion_rate ≠ 1` ("v1 sin FX").

La corrección debe ser **completamente genérica**: `erpnext_proposals` no conoce ninguna app consumidora
ni catálogos de proveedor específicos. La frontera es `Item + contexto económico → resolver genérico → costo`.

## 2. Decisión

### 2.1. Tres monedas distintas, nunca mezcladas

- **Moneda fuente** = moneda de la Buying Price List (o de los fallbacks nativos).
- **Moneda base contable** = `Company.default_currency`. **Es la moneda canónica del análisis económico
  interno** (costo, margen, snapshots).
- **Moneda de presentación** = `Quotation.currency` (campo **nativo**; lo elige quien prepara la propuesta).
  **No se crea ningún selector paralelo**: se respeta el mecanismo nativo (`currency`/`conversion_rate`/
  `price_list_currency`/`plc_conversion_rate`).

### 2.2. Moneda canónica = Company base

El análisis económico opera en **moneda base de la Company**. Justificación:

- El costo laboral proviene de salarios (`Proposal Cost Matrix.avg_costing_rate`) → ya está en base.
- ADR-0017 §7 ya especificaba congelar el costo externo "en moneda base".
- Toda la normalización nativa de ERPNext (`conversion_rate`, `plc_conversion_rate`) ancla en company
  currency; `project_economics` reconcilia en base.

La **presentación** al usuario en `Quotation.currency` se deriva de los importes base con el
`conversion_rate` **nativo** de la Quotation (base → presentación = `1/conversion_rate`). Nunca se
implementa una segunda conversión propia.

### 2.3. Contrato del resolver (`ExternalCost`)

`resolve_external_cost(item_code, uom, transaction_date, company)` devuelve un `ExternalCost` con:
`amount` (normalizado a base), `source`, `source_amount`, `source_currency`, `normalized_currency`
(base), `exchange_rate`, `exchange_date`. Una **única** resolución genérica para `Quotation.items` y
`Quotation.required_items`.

### 2.4. Resolución determinista de Buying Price Lists

Se elimina "una Company = una Buying Price List". Jerarquía determinista y genérica
(`_resolve_buying_price`):

1. Se calculan las Buying Price Lists (`Price List.buying=1`) con precio **vigente** para el Item
   (respetando UOM y `valid_from/valid_upto` con `get_item_price` nativo).
2. Si la lista configurada en `Buying Settings` tiene precio → se usa (desempate nativo).
3. Si exactamente una lista tiene precio → se usa.
4. Si ninguna tiene precio → fallbacks nativos.
5. Si **varias** tienen precio y la configurada no está entre ellas → **`ambiguo_price_list`** (estado
   explícito; **nunca** se elige arbitrariamente la primera).

### 2.5. FX nativo, fail-closed

FX exclusivamente con `erpnext.setup.utils.get_exchange_rate` (consulta `Currency Exchange`, dirección
`for_buying`). No se crea DocType FX propio, tabla paralela ni tasas hardcodeadas. **Si falta la tasa no
se asume 1.0**: el resolver devuelve **`sin_tipo_cambio`** (`amount = None`). La fundación monetaria vive
en `utils/currency.py` (`convert`/`try_convert`/`get_native_exchange_rate`, excepción
`MissingExchangeRate`).

### 2.6. Fecha económica

La referencia es `Quotation.transaction_date` (Fase 2 podrá pasar la fecha del periodo). La fecha del
FX es esa misma fecha.

### 2.7. Frozen costs con trazabilidad

El snapshot por línea deja de ser un `frozen_cost_rate` "pelón". Se persiste, además del importe base
(`*_rate`) y su moneda (`*_currency` = base): **importe original + moneda origen + tipo de cambio**
(`*_source_amount`, `*_source_currency`, `*_exchange_rate`). Así un costo congelado es auditable
históricamente (p. ej. `10 USD × 18 = 180 MXN`). Campos nuevos en `Quotation Item` (custom fields) y en
`Proposal Required Item`.

### 2.8. Estados irresolubles bloquean la formalización

`sin_tipo_cambio` y `ambiguo_price_list` permiten seguir editando el Borrador, pero
`assert_economic_snapshot_complete` los rechaza (fail-closed): una propuesta **no se formaliza** con un
economics que no se pudo determinar correctamente. `resolve_external_cost` **nunca** los degrada a `0`
(que parecería `sin_costo`).

### 2.9. Fallbacks nativos

`last_purchase_rate` y `valuation_rate` los almacena ERPNext en **moneda base**; se usan sin conversión
(`source_currency = base`, `exchange_rate = 1`). El orden se conserva: Buying Item Price →
`last_purchase_rate` → `valuation_rate` → `sin_costo`.

### 2.10. Presentación coherente

- **Rentabilidad Estimada** (`profitability_estimate`): opera en base y presenta en `Quotation.currency`
  convirtiendo los costos con `1/conversion_rate`; los ingresos ya son nativos en esa moneda. Monedas
  distintas **sin** `conversion_rate` → fail-closed.
- **Evaluación Económica / Calendario** (`economic_calendar`): normaliza el ingreso a base con
  `conversion_rate` y expresa todas las magnitudes en base (moneda canónica del forecast interno).
- **Contrato económico del Project** (`project_economics`): ya soporta multimoneda (el ingreso se
  normaliza en la evaluación); solo bloquea, fail-closed, si una Cotización en moneda distinta a la base
  no tiene `conversion_rate`.

### 2.11. Consulta del costo en una moneda objetivo (consumidores)

Economics y snapshots **siguen** normalizando a Company base (no cambia). Además, un **consumidor** (p. ej.
otra app que calcula un `Quotation Item.rate` en `Quotation.currency`) puede pedir el **mismo costo externo
expresado en una moneda objetivo**, sin duplicar lógica FX fuera de `erpnext_proposals`:

```python
resolve_external_cost(item_code, uom, transaction_date, company, target_currency="USD")
```

Semántica:

- **Sin `target_currency`** → comportamiento histórico **idéntico** (normaliza a base; economics y callers
  existentes no cambian).
- **Con `target_currency`** → `ExternalCost.amount` es el costo en esa moneda y `normalized_currency ==
  target_currency`. La conversión es **directa** `source_currency → target_currency` (**nunca**
  `source → base → target`): `source == target` → tasa 1 sin FX; monedas distintas → FX **nativo** por
  `transaction_date`; **falta FX → `sin_tipo_cambio`** (`amount = None`, nunca 1.0).
- La conversión derivada **no se persiste** (no toca el snapshot congelado) y **no** crea Item Prices.
- `ambiguo_price_list` se conserva igual (no hay un costo único que convertir).

**Uso por un consumidor — costo en `Quotation.currency`:**

```python
from erpnext_proposals.erpnext_proposals.utils.item_cost import resolve_external_cost

ec = resolve_external_cost(
    row.item_code, row.get("uom"), quotation.transaction_date, quotation.company,
    target_currency=quotation.currency,
)
if ec.amount is None:          # sin_tipo_cambio / ambiguo_price_list → decisión del consumidor
    ...                         # no asumir 0 ni tasa 1
else:
    costo_en_quotation_currency = ec.amount   # ya en quotation.currency
```

## 3. Consecuencias

- No existe ninguna suma directa entre monedas distintas. El caso **Company MXN + Quotation MXN + Buying
  Price List MXN** es **idéntico** al comportamiento previo (factor 1.0, tasa 1.0).
- El snapshot económico crece con la trazabilidad de origen (6 campos por tipo de línea, todos
  read-only). No se agregan campos de recurrencia (siguen diferidos a Fase 2).
- Requiere `bench migrate` por sitio (custom fields nuevos + campos del child DocType).
- La ambigüedad de listas y la falta de FX son ahora estados de negocio explícitos que el usuario resuelve
  (configurar la Buying Price List, capturar el `Currency Exchange`), no fallos silenciosos.

## 4. Alternativas descartadas

- **DocType/tabla FX propia o tasas hardcodeadas** → se reutiliza `Currency Exchange` + `get_exchange_rate`
  nativos. Rechazada.
- **Asumir `conversion_rate = 1` / tasa 1.0 cuando falta FX** → produce márgenes falsos. Rechazada
  (fail-closed).
- **Normalizar a `Quotation.currency` como moneda canónica interna** → el costo laboral (salarios) y los
  snapshots quedarían fuera de la moneda contable; rompe la reconciliación en base de ADR-0020. Rechazada.
- **Selector de moneda propio en la Quotation** → duplica `Quotation.currency` nativo. Rechazada.
- **Elegir la primera Buying Price List cuando hay varias** → decisión arbitraria no auditable. Rechazada
  (estado `ambiguo_price_list`).

## 5. Decisiones diferidas

- FX por periodo (Fase 2C): la fecha del tipo de cambio por ocurrencia del calendario (hoy toda la
  evaluación usa `transaction_date`).
- Conversión de la presentación del Calendario Económico a `Quotation.currency` (hoy el calendario se
  expresa en base; el reporte comercial de Rentabilidad sí presenta en Quotation currency).
- Supplier Quotation como fuente explícita de costo por oportunidad (ya diferida en ADR-0017 §14).
