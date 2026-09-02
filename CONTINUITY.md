# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-02
**Rama activa:** `feat/required-items` (base `upstream/version-16` = v0.16.0)
**Tarea actual:** Fase 1 de **ADR-0017** (Items requeridos + modelo económico aditivo). Implementación
completa y verde; lista para `/ship commit`. Fase 2 (recurrencia) documentada pero **no** implementada.

---

## Recuperación rápida

`Quotation.items` = Items vendidos; nuevo child **`Proposal Required Item`** (`Quotation.required_items`) =
Items necesarios pero **no vendidos**. Ambos son Items nativos y alimentan el **mismo** resolver N:M
Item↔Scope y la **misma** `Quotation Scope Item`. Modelo de costo **aditivo**: costo externo (nativo,
gateado por `is_purchase_item`) + costo laboral (Scope Items).

## Qué se implementó (Fase 1)
- DocType `Proposal Required Item` (`item`, `qty`, `uom` + snapshot `frozen_cost_*`/`cost_locked`) +
  custom field `required_items`.
- Generación / `add_missing_scope_items_from_items` / `resync` iteran **items ∪ required_items**
  (`_source_item_codes`); clave de dedup `(item_code, scope_item)` intacta.
- `utils/item_cost.resolve_external_cost`: `is_purchase_item` → `get_item_price` (nativo, Buying Settings)
  → `last_purchase_rate` → `valuation_rate`. Se eliminó el `covered_by_scope` (fix reventa).
- Freeze del costo externo en Borrador→En Revisión (Quotation Item: `proposal_frozen_cost_*`; Required
  Item: `frozen_cost_*`); el reporte lee snapshot en submitted → rentabilidad histórica inmutable.
- Rentabilidad: ingresos − costo de compra (vendidos/requeridos comprables) − costo de esfuerzo.
- 22 tests nuevos (datos genéricos); suite completa **427 OK**. ruff/mkdocs verdes. Bump **0.17.0**.

## Pendientes / notas
- **Textos de UI** (descripción del campo `required_items` y labels internos): el usuario los quiere pulir
  **después** — el commit avanza con la redacción actual; revisar wording en un cambio posterior.
- **Fase 2 (recurrencia económica):** obligatoria de corto plazo, documentada en ADR-0017 con restricciones
  de compatibilidad; no implementar sin autorización.
- **Bug latente** `task_by_scope` (dependencias con scope repetido entre Items): a Issue separado; no bloquea.
- **Operativo:** `bench migrate` en dev sin worker deja locks huérfanos de Role Profile (erpnext_custom) →
  `DocumentLockedError`. Fix: `rm sites/<site>/locks/*.lock` + migrate. Fondo pendiente (worker en dev).
- Migrado: site de tests y `proposals.dev`. Scripts en `one_offs/` (fixture updater) — no commiteados.

## No repetir
- El costo externo y el laboral son **aditivos e independientes** (no anular uno por el otro).
- Costo externo **solo** si `Item.is_purchase_item`; pricing **nativo** (`get_item_price`), sin queries propias ni Supplier Quotation automática.
- Required Items = selección por-Quotation (UX), **no** de catálogo; packs/loader sin cambios.
- **Nunca** datos de cliente en archivos trackeados del repo.
