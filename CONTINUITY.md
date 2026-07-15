# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-07-14
**Rama activa:** `feat/scope-catalog-resync`
**Tarea actual:** Issue #27 — sincronización explícita del alcance con el catálogo en Borrador (`resync_scope_from_catalog`). Implementado; pendiente commit/PR.

---

## Recuperación rápida

Estoy trabajando en:
Issue #27: botón **"Sincronizar alcance desde catálogo"** que hace update + remove + add sobre
las filas `auto_generated=1` de una propuesta en Borrador, preservando filas manuales e
`include_in_proposal`. Diseño cerrado en el comentario del Issue #27.

Plan que estoy siguiendo:
Diseño acordado en Issue #27 (fuente de verdad). Sin cambio de esquema. No incluye `phase → Link`
ni `manual_override`.

Objetivo inmediato:
Commit + push + PR de `feat/scope-catalog-resync` a `version-16`.

Criterio de avance:
Suite verde (128 OK), linters + mkdocs strict OK, docs actualizadas, PR abierto.

---

## Estado actual

### Ya cerrado
- PR #26: catálogo `Proposal Phase` + pruebas de inmutabilidad.
- PR #28: documentación — anatomía del PDF + umbral `sequence >= 500`; Limitación 7.
- **Issue #27 (esta rama):** método whitelisted `resync_scope_from_catalog` + botón renombrado +
  flujo confirmar→guardar→sincronizar→recargar + 6 tests + docs. `validate` sigue append-only.
- `proposals-acti.dev`: clon saneado de ActiGlobal con demo funcional (`SAL-QTN-2026-00001`).

### En progreso
- Commit/PR de `feat/scope-catalog-resync`.

### Pendiente inmediato
1. Commit + push + PR de esta rama.
2. `phase` como Link a Proposal Phase (+ snapshot). Ver [[design_phase_link_pendiente]]. **Tema separado, no en esta rama.**
3. Diseño de `Proposal Scope Template` (herencia Item → alcance).

### No repetir
- **NUNCA** mezclar `phase → Link` con esta rama (#27 es solo el resync).
- El re-sync **solo** en Borrador; se congela en *En Revisión* (no tocar ese comportamiento).
- `docs/referencia/` es **autogenerada** (`scripts/generate_reference.py`) — regenerar, no editar a mano.
- Remoto es `upstream` (no `origin`). No commitear en `version-16`.

---

## Decisiones vigentes (Issue #27)
- `auto_generated=1` = propiedad del catálogo (se actualiza/elimina en resync); `auto_generated=0` = propiedad de la propuesta (nunca se toca).
- Autosave = append-only; botón = resync completo con confirmación.
- El resync **sobrescribe** ediciones manuales sobre filas auto (MVP, sin `manual_override`); preserva `include_in_proposal`.
- Campos controlados por catálogo: `sequence, code, title, description, deliverable, phase, activity_type, designation, estimated_hours`.

## Otras decisiones vigentes
- `phase` en la propuesta debe ser Link + snapshot congelado (pendiente, [[design_phase_link_pendiente]]).
- La propuesta es inmutable tras *En Revisión*; cambios → nueva versión.
- `designation` se muestra al cliente en el PDF — decidir si ocultarla (costos/margen NO se filtran).

---

## Archivos relevantes ahora

### Leer primero
- `utils/quotation.py` — `resync_scope_from_catalog`, `_catalog_rows_for_items`, `_CATALOG_CONTROLLED_FIELDS`; `_generate_scope_items` (append-only, sin cambios).
- `public/js/quotation.js` — botón "Sincronizar alcance desde catálogo".
- `tests/test_scope_catalog_resync.py` — 6 casos.

### Probablemente editar (etapa siguiente, no ahora)
- `scope_item.json` / `quotation_scope_item.json` (phase → Link + snapshot), nuevo `Proposal Scope Template`.

### No tocar
- `docs/referencia/` (generada). Congelamiento en *En Revisión*.

---

## Riesgos / cuidados
- `bench run-tests` solo en `test-erpnext_proposals.localhost`.
- CI corre semgrep (frappe rules): sin `frappe.db.commit()`, `throw` con `_()`, type hints en whitelisted — verificado.
- `proposals-acti.dev` es clon de producción: escritura una acción a la vez, con autorización.

---

## Información faltante
- Diseño final de `Proposal Scope Template` y herencia Item → alcance.
- Decisión: ¿ocultar `designation` del PDF cliente?
