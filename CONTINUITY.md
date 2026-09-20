# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-20
**Rama activa:** `feat/loader-item-purchase-econ-rules` (base `upstream/version-16` = v0.24.0; objetivo **0.25.0**)
**Tarea actual:** Loader — soporte declarativo de `is_purchase_item` y `economic_behavior_rules`. En ciclo `/ship`, detener en PR.

---

## Recuperación rápida

Estoy trabajando en:
Ampliar el loader del catálogo (`catalog_data/catalog_loader.py`) para reproducir la config canónica del
producto recurrente no-comprable `Legal Officer as a Service` (LOAS-JUR-CORP-001) — sin rediseño.

Plan que estoy siguiendo:
Petición del usuario (cambio mínimo en el loader existente) + ADR-0018 (comportamiento económico).

Objetivo inmediato:
`/ship` hasta PR contra `version-16` (bump 0.25.0). Sin merge, sin release del pack, sin tocar producción.

Criterio de avance:
PR abierto, CI verde, alcance limitado a is_purchase_item + economic_behavior_rules + tests.

---

## Estado actual

### Ya cerrado
- `_seed_items` administra `is_purchase_item` (clave ausente = no toca).
- Nuevo `_seed_economic_behavior_rules` (por Company, idempotente, no borra reglas no declaradas, dry_run
  create/update/unchanged); registrado en `capabilities()`; invocado tras `_seed_items`.
- Tests: `test_is_purchase_item_managed`, `test_economic_behavior_rules_managed` (test_catalog_loader → 17).
- Bump 0.25.0 + CHANGELOG (renombra v0.24.0) + arquitectura (fila del loader).

### Pendiente inmediato
1. `/ship commit` → `/ship push` → `/ship pr`. Detener en PR.
2. Después (fuera de este PR): re-corte/release del **pack privado** (working diverge del sello 1.25.0 por
   `is_purchase_item` + `economic_behavior_rules`) — NO iniciar sin autorización.

### No repetir
- El pack **no** versiona `is_purchase_item`/`economic_behavior_rules` hasta que ESTE loader se libere/instale.
- `test_09b_duplicate_item_line_rejected_by_erpnext` (#60) falla solo local (`allow_multiple_items=1`); pasa en CI.
- proposals.dev sigue rezagado en la migración V1 del Print Format (drift preexistente, ajeno a este cambio).

---

## Decisiones vigentes
- Campos administrados del loader: clave presente fija; ausente no toca; null limpia. `is_purchase_item` sigue ese patrón.
- `economic_behavior_rules` se siembra por Company sin borrar reglas ajenas ni tocar otros campos de Proposal Settings.

---

## Archivos relevantes ahora
### Leer primero
- `erpnext_proposals/erpnext_proposals/catalog_data/catalog_loader.py` (`_seed_items`, `_seed_economic_behavior_rules`)
### No tocar
- Print Format, Proposal Template, Sections, `facturacion_mexico`, producción, pack (release).

---

## Riesgos / cuidados
- `test_09b` (#60) es la única falla de suite y es ambiental local.

## Información faltante
- Ninguna para cerrar el PR. El release del pack es un paso posterior separado.
