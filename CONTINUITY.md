# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-30
**Rama activa:** `feat/procurement-task-handoff` (base `upstream/version-16` = v0.31.0 → objetivo **v0.32.0**)
**Tarea actual:** PR — handoff de compras por obligación + programa mínimo por fallbacks de Scope + Ganada→Project incondicional.

---

## Recuperación rápida

Estoy trabajando en:
Entregar, sobre la ruta única `Item/Required → Scope Item → Proposal Phase → Quotation Scope Item → Task`,
tres bloques funcionales ya validados (835 OK):

1. **Handoff de compras por obligación** — cada ocurrencia comprable (vendida o requerida) genera UNA Task
   individual de compra vía `default_purchase_scope_item`; se retira hacia adelante el handoff de lista única
   (`procurement.py`); el package de Gestión de Compras se conserva como esfuerzo interno.
2. **Integridad compromiso → programa** — Item vendido sin Scope propio → `default_commitment_scope_item`
   (Task de compromiso por ocurrencia); identidad `(source_row, scope_item)`; la fase vive en Scope Item.
3. **Ganada → Project incondicional** — toda Quotation que llega a «Ganada» crea Project + programa; la
   transición valida fail-closed (template + fila ejecutable + fase + Project Type + prerrequisitos de
   fallback). `auto_create_project_on_won` queda DEPRECADO/oculto (ya no gobierna la creación).

Plan que estoy siguiendo:
3 commits (`aedcff2`, `978c931`, `c048246`) + bump MINOR a v0.32.0 + CONTINUITY. PR hacia `version-16`.

Objetivo inmediato:
Dejar el PR listo para merge (el merge lo hace el usuario).

Criterio de avance:
Suite completa **835 OK**; ruff OK; `mkdocs build --strict` OK; migrate limpio en dev/test.

---

## Estado actual

### Ya cerrado (esta rama)
- **`aedcff2`:** handoff mínimo de compras (superado hacia adelante por `c048246`; sin código muerto).
- **`978c931`:** UX mínima de Scope Item (`moment` oculto; offset/duración = planeación PMO opcional).
- **`c048246`:** fallbacks de Scope (compromiso/compra por ocurrencia) + subjects humanos + retiro de
  `procurement.py` + Ganada→Project incondicional + validación fail-closed + deprecación del toggle.

### Pendiente inmediato
1. Gate `pr-ready` → push + PR (autorizado por la invocación de `/ship pr`).
2. Merge: **lo ejecuta el usuario** (no autorizado a Claude).
3. Tras merge: `/sync-check` + `/ship release` (tag/Release v0.32.0).

### No repetir / atención
- No es una «simplificación masiva de Scope»: fue UX mínima, no rediseño.
- Forward-only: cero backfill; históricos/roots intactos; addendas doc-scoped; motor económico sin cambios;
  sin jerarquía fuera de Proposal Phase; sin campos nuevos en Task.
- `auto_create_project_on_won`: deprecado/oculto, conservado solo por compatibilidad (retiro físico futuro).

## Decisiones vigentes
- Opción A: creación de Project incondicional al ganar; el toggle ya no gobierna.
- Settings nuevos: `default_commitment_scope_item`, `default_purchase_scope_item` (Links a Scope Item).

## Información faltante
- Ninguna para el PR.
