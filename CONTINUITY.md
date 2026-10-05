# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-10-01
**Rama activa:** `feat/scope-item-ux-catalog` (base `upstream/version-16` = v0.32.0 → objetivo **v0.33.0**)
**Tarea actual:** PR — simplificación UX del catálogo `Scope Item` (solo presentación).

---

## Recuperación rápida

Estoy trabajando en:
Reorganizar el DocType `Scope Item` para que el catálogo sea fácil de mantener, **sin tocar lógica**.
Cambio exclusivamente de metadata del DocType propio + un ajuste de doc de usuario:

- Secciones **expandidas**: "Información principal" (code, title, phase), "Costeo y esfuerzo"
  (estimated_hours, default_designation, default_activity_type), "Items asociados" (erpnext_items).
- Secciones **colapsadas**: "Contenido para propuesta" (description, deliverable, visible_in_proposal),
  "Opciones" (enabled, sequence, is_internal_cost_task), "Planeación PMO".
- Legacy `erpnext_item` → `hidden=1` (se conserva por compatibilidad; la relación vigente es `erpnext_items`).
  `moment` permanece oculto.
- `title_field=title` + `show_title_field_in_link=1` (identificación por título). `autoname=field:code` intacto.

Plan que estoy siguiendo:
Commit funcional (`9a23a1f`) + bump MINOR a v0.33.0 + CONTINUITY → push → PR hacia `version-16`.

Objetivo inmediato:
Dejar el PR listo para revisión/merge (el merge lo hace el usuario).

Criterio de avance:
36 tests de Scope Item OK (generation/resync/row-identity); `mkdocs --strict` OK; migrate limpio en
`proposals.dev` y en el site de tests; validación de layout vía `frappe.get_meta`.

---

## Estado actual

### Alcance (estricto)
Solo `erpnext_proposals/.../doctype/scope_item/scope_item.json` + `docs/usuario/scope-items-reutilizables.md`.
**No** se tocó: Quotation, Quotation Scope Item, resync, costeo, generación de alcance, Designation /
Activity Type / Proposal Cost Matrix, ni históricos.

### Pendiente inmediato
1. Gate `pr-ready` → push + PR (autorizado por la invocación de `/ship`).
2. Revisión CodeRabbit si aplica.
3. Merge: **lo ejecuta el usuario** (`/ship merge`).
4. Tras merge: `/sync-check` + `/ship release` (tag/Release v0.33.0).

### No repetir / atención
- Cambio **100% presentación/metadata**: Property-less (DocType propio, no Custom Field). `migrate` lo aplica.
- Históricos intactos por construcción: `read_only`/`hidden`/orden no alteran datos; `name` no cambia.
- El ajuste específico por oportunidad en Quotation Scope Item **queda fuera de alcance** (ronda futura).

## Decisiones vigentes
- Scope Item = catálogo de actividad estándar reutilizable; Quotation = copia específica; fallback intacto.
- SemVer MINOR por precedente (v0.31.0 fue cambio UX/metadata de Scope Item clasificado MINOR).

## Información faltante
- Ninguna para el PR.
