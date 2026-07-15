# ADR-0003: Sincronización del alcance con el catálogo (Borrador)

**Fecha:** 2026-07-14
**Status:** Cerrado — implementado (PR #27, rama `feat/scope-catalog-resync`)
**Rama:** feature/scope-catalog-resync → version-16
**Issue:** #27

---

## Contexto

El alcance de una propuesta (`quotation_scope_items`) se genera desde el catálogo `Scope Item`
en `validate` (`_generate_scope_items`), de forma **append-only**: solo agrega combinaciones
`(item_code, scope_item)` faltantes; nunca actualiza ni elimina filas existentes.

Esto dejaba dos huecos mientras la propuesta está en **Borrador** (antes de congelarse en *En
Revisión*):

- Editar el catálogo (horas, título, fase, perfil) no se reflejaba en propuestas ya generadas.
- Deshabilitar/borrar un `Scope Item`, o quitar un Item de la cotización, dejaba filas huérfanas.
- El botón "Regenerar alcance" prometía más de lo que hacía (solo agregaba).

La copia congelada **posterior a *En Revisión*** es intencional (inmutabilidad histórica) y no se
toca; el problema era exclusivamente el rango Borrador.

---

## Decisión

**Dos disparadores separados:**

- `validate` (autosave): permanece **append-only**, no destructivo. No pierde ediciones hechas
  en la tabla al guardar.
- Botón **"Sincronizar alcance desde catálogo"** → método whitelisted
  `resync_scope_from_catalog` (solo Borrador): sincronización completa **update + remove + add**.

**Modelo de propiedad de las filas:**

- `auto_generated=1` → **propiedad del catálogo**: se actualiza/elimina en la sincronización.
- `auto_generated=0` → **propiedad de la propuesta**: nunca se toca ni elimina.

**Campos controlados por catálogo** (los únicos que refresca el resync): `sequence`, `code`,
`title`, `description`, `deliverable`, `phase`, `activity_type`, `designation`, `estimated_hours`.
Se preservan `include_in_proposal`, `auto_generated` y los campos de costeo/congelamiento
(`costing_rate`, `rate_source`, `rate_locked`, `rate_locked_on`).

**Guarda de servidor** (las tres simultáneamente): `docstatus == 0` **y**
`workflow_state == "Borrador"` **y** `proposal_template` informado; además
`check_permission("write")`.

**Flujo de UI:** confirmar → guardar si hay cambios pendientes → sincronizar → recargar (así el
resync opera sobre los Items realmente guardados).

---

## Consecuencias

- El congelamiento en *En Revisión* queda intacto; el resync se rechaza fuera de Borrador.
- En el flujo del botón, el guardado previo (append-only) ya agrega las combinaciones nuevas; el
  aporte neto del resync suele ser update + remove. El efecto combinado es la sincronización total.
- Sin cambio de esquema: el modelo se apoya en el campo existente `auto_generated`.
- La sincronización **sobrescribe** ediciones manuales hechas sobre filas generadas desde catálogo.

---

## Alternativas descartadas

- **`manual_override` por fila** (preservar ediciones manuales sobre filas auto): descartado para
  el MVP por costo/complejidad; las personalizaciones permanentes se hacen con filas manuales
  (`auto_generated=0`). Queda como posible mejora futura.
- **Re-sync automático en cada `validate`**: descartado — sería destructivo (borraría ediciones
  recién hechas en la grid al guardar). Por eso la sincronización completa es explícita (botón).

---

## Fuera de alcance

- Conversión de `phase` a Link con `Proposal Phase` (tema separado).
- Cualquier cambio al congelamiento post-*En Revisión*.
