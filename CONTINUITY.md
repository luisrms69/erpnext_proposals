# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-26
**Rama activa:** `fix/external-cost-zero-rate` (base `upstream/version-16` = v0.30.0 → objetivo **v0.30.1**)
**Tarea actual:** PR — fix del costo externo con Buying Item Price rate 0.

---

## Recuperación rápida

Estoy trabajando en:
Corregir un bug genérico de `resolve_external_cost` (v0.30.0): un Buying Item Price existente con
`price_list_rate = 0` terminaba en `sin_costo` por evaluar el rate por truthiness.

Plan que estoy siguiendo:
Distinguir EXISTENCIA del precio (`price_list is not None`) de su VALOR (`rate == 0`). Un Item Price
encontrado con rate 0 es costo válido `buying_item_price`; ausencia de Item Price conserva fallbacks /
`sin_costo`. Guarda de cero: un costo fuente 0 se conserva 0 sin disparar FX.

Objetivo inmediato:
Abrir el PR hacia `version-16` con el bump a v0.30.1 (gate `pr-ready`).

Criterio de avance:
Suite completa **818 OK / 1 skip**; `test_multicurrency_external_cost` 20; ruff OK.

---

## Estado actual

### Ya cerrado (esta rama)
- **Fix (commit `287cbfc`):** `utils/item_cost.py` — `_price_from_list` (None si no hay fila),
  `_resolve_buying_price` (`if rate is not None`), `resolve_external_cost` (discrimina por
  `price_list is not None` + guarda de cero). Tests +3 en `test_multicurrency_external_cost.py`.

### Pendiente inmediato
1. Gate `pr-ready`: push + creación del PR (una sola autorización).
2. Tras merge: `/sync-check` + `/ship release` (tag + GitHub Release v0.30.1).

### No repetir / atención
- Alcance restringido a `utils/item_cost.py` + su test (+ bump/CONTINUITY del propio `/ship pr`).
- Los fallbacks (`last_purchase_rate`/`valuation_rate`) SIGUEN usando truthiness: 0 = sin dato (correcto);
  solo el path de Buying Item Price distingue encontrado-0 de no-encontrado.

---

## Decisiones vigentes
- Un Buying Item Price encontrado (incluye rate 0) es `buying_item_price`; existencia ≠ valor.
- Costo fuente 0 se conserva 0 en cualquier moneda, sin disparar FX (nunca `sin_tipo_cambio` por un cero).
- Multimoneda / `target_currency` / FX / snapshots (ADR-0024) intactos.

## Información faltante
- Ninguna para el PR.
