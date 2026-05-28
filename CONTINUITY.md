# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-05-28
**Rama activa:** `fix/project-creation-ganada-guards`
**Tarea actual:** Commit pendiente — 3 bugfixes en flujo Ganada + creación de proyecto

---

## Recuperación rápida

Estoy trabajando en:
Rama `fix/project-creation-ganada-guards` con 3 bugfixes validados en GUI, listos para commit.

Plan que estoy siguiendo:
/ship commit → /ship push → /ship pr → merge a version-16

Objetivo inmediato:
Escribir CONTINUITY.md, hacer commit de 4 archivos, push y PR.

Criterio de avance:
PR abierto en GitHub con los 3 fixes, CI verde.

---

## Estado actual

### Ya cerrado
- Issue #18 — hide native buttons + Ganada workflow state (PR #21, mergeado)
- Issue #13 — versionado de propuestas (PR #19, mergeado)
- Issue #16 — PDF polish (PR #16, mergeado)
- Issue #14 — submit quotations on review + PDF attach (PR #14, mergeado)

### En progreso
- `fix/project-creation-ganada-guards` — 3 bugfixes descubiertos en GUI testing post-PR #21

### Pendiente inmediato
1. Confirmar CONTINUITY.md (este archivo)
2. Commit: `proposal_versioning.py`, `project.py`, `quotation.js`, `CONTINUITY.md`
3. Push y PR a `version-16`

### No repetir
- No usar `cur_frm` en JS — Frappe v16 lo deprecó, semgrep CI lo bloquea.
- Remote es `upstream` (no `origin`). Excepción: `frappe-infrastructure` usa `origin`.
- No commitear en `version-16` directamente.
- CONTINUITY.md se actualiza con `/update-continuity`, nunca manualmente.
- `ruff check` debe correr solo sobre archivos del commit, no sobre `one_offs/`.

---

## Decisiones vigentes

- **`Ganada`** es el único estado donde se puede crear Proyecto y donde `Sales Order` es válida.
- **`Sales Order`** solo visible cuando `workflow_state === "Ganada"` AND `proposal_project` existe — enforces project-first flow.
- **Nombre default de proyecto:** `"{customer_name} — {proposal_group}"` cuando `proposal_title` está vacío — garantiza unicidad.
- **`proposal_group`** NO es unique en DB — es intencional (versiones v1/v2/v3 comparten group). La unicidad de propuesta viva se gestiona a nivel app con `assert_single_live_proposal_for_group`.
- **`declare_enquiry_lost`** bloqueado en backend vía `extend_doctype_class` mixin.
- `one_offs/` nunca se commitea. 15 scripts retenidos son utilidades activas de dev.

---

## Archivos relevantes ahora

### Leer primero
- `CONTINUITY.md` — este archivo
- `erpnext_proposals/erpnext_proposals/utils/proposal_versioning.py` — guard `assert_can_create_project`
- `erpnext_proposals/erpnext_proposals/utils/project.py` — lógica de creación de proyecto
- `erpnext_proposals/public/js/quotation.js` — botón Sales Order condición `proposal_project`

### Probablemente editar
- Nada — fixes completados, pendiente solo commit/push/PR

### No tocar
- `version-16` directamente
- `test-erpnext_proposals.localhost` manualmente

---

## Issues abiertos

| # | Título | Prioridad |
|---|---|---|
| #17 | feat: auto-populate proposal_group desde Frappe CRM Opportunity | Media |
| #15 | feat: selector de paleta de colores por cotización | Baja |
