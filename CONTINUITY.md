# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-05-30
**Rama activa:** `docs/mkdocs-standard-fase1-fase2`
**Tarea actual:** PR #24 abierto — normalización MkDocs pendiente de merge

---

## Recuperación rápida

Estoy trabajando en:
PR #24 `docs(proposals): normalize mkdocs structure and documentation` — en revisión.

Plan que estoy siguiendo:
`facturacion_mexico/working_docs/active/PLAN_MKDOCS_SETUP_ECOSISTEMA.md`

Objetivo inmediato:
Esperar merge del PR #24, luego /sync-check y actualizar tabla de transición en frappe-infrastructure.

Criterio de avance:
PR #24 mergeado a `version-16`.

---

## Estado actual

### Ya cerrado
- PR #23 — permission guards, role fixture, project idempotency fix
- PR #22 — project guard, SO button, default project name
- Normalización MkDocs (Fases 1–4+7) commiteada en rama

### En progreso
- PR #24 — normalización MkDocs — abierto, pendiente review/merge

### Pendiente inmediato
1. Merge PR #24
2. /sync-check post-merge
3. Actualizar tabla de transición en `frappe-infrastructure/docs/architecture/documentation-standard.md`
4. ADRs candidatos (idempotencia proyecto, permission guards, submit en En Revision) — tarea separada

### No repetir
- No usar `cur_frm` en JS — Frappe v16 lo deprecó.
- Remote es `upstream` (no `origin`).
- No commitear en `version-16` directamente.
- `docs/referencia/` es generada — no editar manualmente.
- Tests Frappe requieren `bench run-tests`, no `pytest` directo.

---

## Decisiones vigentes

- Estado "Ganada" es workflow state real — transición "Marcar como Ganada" desde "Enviada al Cliente"
- Botón "Crear Proyecto" requiere docstatus=1 Y workflow_state="Ganada"
- Submit automático ocurre en transición Borrador → En Revision (doc_status=1 en fixture)
- `assert_can_manage_proposals()` permite System Manager + Proposals Manager
- `docs/referencia/` generada con `python3 scripts/generate_reference.py`
- `frappe-multisite --docs erpnext_proposals` disponible en puerto 8767

---

## Archivos relevantes ahora

### Leer primero
- PR #24: https://github.com/luisrms69/erpnext_proposals/pull/24

### Probablemente editar post-merge
- `frappe-infrastructure/docs/architecture/documentation-standard.md` — eliminar fila erpnext_proposals de tabla de transición

### No tocar
- `docs/referencia/` — generado, no editar manualmente
- `version-16` directamente

---

## Riesgos / cuidados

- Anchor links INFO en `referencia/api.md` — no bloquean build, deuda del generador
- ADRs candidatos NO incluidos en PR #24 — pendiente commit posterior
