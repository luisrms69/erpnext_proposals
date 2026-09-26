# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-26
**Rama activa:** `feat/multicurrency-external-cost` (base `upstream/version-16` = v0.29.0 → objetivo **v0.30.0**)
**Tarea actual:** PR — costo externo multimoneda (ADR-0024) + extensión `target_currency` para consumidores.

---

## Recuperación rápida

Estoy trabajando en:
Hacer genérico y multimoneda el costo externo de compra en `erpnext_proposals`, sin conocimiento de
ninguna app consumidora. La frontera es `Item + contexto económico → resolver genérico → costo`.

Plan que estoy siguiendo:
Moneda canónica del análisis económico = **Company base**. El costo externo se normaliza a base con FX
NATIVO de ERPNext (`Currency Exchange`) y se congela con trazabilidad de origen. La presentación al usuario
usa `Quotation.currency` (nativo, `conversion_rate`). Un consumidor puede pedir el costo en una moneda
objetivo con `resolve_external_cost(..., target_currency=...)` (conversión directa source→target).

Objetivo inmediato:
Abrir el PR hacia `version-16` con el bump a v0.30.0 (gate `pr-ready`).

Criterio de avance:
Suite completa **815 OK / 1 skip**; ruff+prettier OK; mkdocs strict OK; migrate dev+test limpios. QA de
`acti_customs` (retro `target_currency`) aceptado.

---

## Estado actual

### Ya cerrado (esta rama)
- **Multicurrency (commit `48d3d3c`):** `utils/currency.py` (FX nativo, fail-closed `MissingExchangeRate`);
  `item_cost.resolve_external_cost` → `ExternalCost` (normaliza a base, trazabilidad origen, múltiples
  Buying Price Lists deterministas, `sin_tipo_cambio`, `ambiguo_price_list`); frozen snapshot con moneda
  base + importe/moneda origen + FX (+4 campos en Quotation Item y en Proposal Required Item);
  `profitability_estimate` presenta en Quotation currency; `economic_calendar` normaliza ingreso a base;
  `project_economics` soporta multimoneda. ADR-0024 + arquitectura.md.
- **Extensión `target_currency` (commit `3d970db`):** `resolve_external_cost(..., target_currency=...)` —
  consulta del costo en una moneda objetivo con conversión directa source→target, sin persistir ni crear
  Item Prices; sin target → comportamiento idéntico. ADR-0024 §2.11 + tests A–E.

### Pendiente inmediato
1. Gate `pr-ready`: push + creación del PR (una sola autorización).
2. Tras merge: `/sync-check` + `/ship release` (tag + GitHub Release v0.30.0).

### No repetir / atención
- Economics y frozen snapshots **siempre** en Company base; `target_currency` es solo para consumidores y
  NO se persiste.
- FX exclusivamente nativo (`get_exchange_rate`); falta tasa → `sin_tipo_cambio` (nunca 1.0).

---

## Decisiones vigentes
- Moneda canónica del análisis económico = `Company.default_currency`.
- Presentación en `Quotation.currency` vía `conversion_rate` nativo.
- Resolver único para `Quotation.items` y `required_items`.
- Cero lógica de apps consumidoras (Microsoft/acti_customs) en `erpnext_proposals`.

## Fuera de alcance
- Presentación del Calendario Económico en Quotation currency (hoy en base); FX por periodo (ADR-0024 §5).

## Información faltante
- Ninguna para el PR.
