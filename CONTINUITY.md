# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-05-28
**Rama activa:** `continuity/update-after-pr22`
**Tarea actual:** Commit listo — permission guards + role fixture + project idempotency fix

---

## Recuperación rápida

Estoy trabajando en:
Rama `continuity/update-after-pr22` con commit pendiente de ejecutar.
Incluye: guard de permisos en endpoints críticos, Proposals User en fixture,
fix de idempotencia en "Ver / Actualizar Proyecto", y 51 tests nuevos.

Plan que estoy siguiendo:
/ship commit → /ship push → /ship pr → merge a version-16

Objetivo inmediato:
Escribir CONTINUITY.md, ejecutar commit, push y PR.

Criterio de avance:
PR abierto en GitHub con CI verde.

---

## Estado actual

### Ya cerrado
- PR #22 — project guard, SO button, default project name (mergeado)
- PR #21 — hide native buttons + Ganada workflow state (mergeado)
- PR #19 — proposal versioning (mergeado)
- PR #16 — PDF polish (mergeado)

### En progreso
- `continuity/update-after-pr22` — permission guards + idempotency fix + tests

### Pendiente inmediato
1. Confirmar CONTINUITY.md (este archivo)
2. Commit 10 archivos en esta rama
3. Push y PR a `version-16`

### No repetir
- No usar `cur_frm` en JS — Frappe v16 lo deprecó, semgrep CI lo bloquea.
- Remote es `upstream` (no `origin`).
- No commitear en `version-16` directamente.
- CONTINUITY.md se actualiza con `/update-continuity`, nunca manualmente.
- No instalar Playwright ni herramientas nuevas para validación GUI — usar curl/bench.

---

## Decisiones vigentes

- `assert_can_manage_proposals()` permite System Manager + Proposals Manager.
  Proposals User está explícitamente bloqueado en endpoints críticos.
- `assert_can_create_project` NO verifica `proposal_project` — la idempotencia
  está en `project.py`. Versiones superseded bloqueadas por `superseded_by_proposal`.
  Ver test_17 y test_ganada_with_existing_project_passes_guard.
- `Proposals User` ahora en `fixtures/role.json` — faltaba desde el inicio.
- Permisos de catálogo (Proposal Section, Template, Scope Item), allow_self_approval,
  y allow_edit en Rechazada quedan pendientes para siguiente tarea.

---

## Archivos relevantes ahora

### Leer primero
- `CONTINUITY.md` — este archivo
- `utils/permissions.py` — helper assert_can_manage_proposals
- `tests/test_proposal_permissions.py` — tests de guards de rol

### Probablemente editar
- Nada — código listo para commit

### No tocar
- `version-16` directamente

---

## Validación GUI pendiente

- Permisos Proposals User — sin usuario disponible en proposals.dev
- Rechazada con proyecto no puede versionar — no validado en GUI

---

## Issues abiertos

| # | Título | Prioridad |
|---|---|---|
| #17 | feat: auto-populate proposal_group desde Frappe CRM Opportunity | Media |
| #15 | feat: selector de paleta de colores por cotización | Baja |

### Pendiente de issue
- Permisos catálogo maestro (Proposals User puede editar Proposal Section/Template/Scope Item)
- allow_self_approval en todas las transiciones
- allow_edit = Proposals User en estado Rechazada
