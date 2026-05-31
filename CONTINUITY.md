# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-05-30
**Rama activa:** `docs/mkdocs-standard-fase1-fase2`
**Tarea actual:** Normalización MkDocs completa — pendiente commit y PR

---

## Recuperación rápida

Estoy trabajando en:
Rama única `docs/mkdocs-standard-fase1-fase2` con todo el trabajo de normalización MkDocs:
Fase 1+2 (commit a36ef21) y Fase 4+3+7 listos para segundo commit.

Plan que estoy siguiendo:
`facturacion_mexico/working_docs/active/PLAN_MKDOCS_SETUP_ECOSISTEMA.md`

Objetivo inmediato:
Commit Fase 4+3+7, luego PR a `version-16`.

Criterio de avance:
PR abierto, `mkdocs build --strict` limpio, 36 tests pasando.

---

## Estado actual

### Ya cerrado
- Commit a36ef21: Fase 1+2 — working_docs/, referencia generada, print-formats.md
- Discrepancias críticas corregidas en docs/usuario/ (estado Ganada, condición botón proyecto)
- PR #23 — permission guards, role fixture, project idempotency fix
- PR #22 — project guard, SO button, default project name

### En progreso
- Rama `docs/mkdocs-standard-fase1-fase2` — pendiente segundo commit

### Pendiente inmediato
1. Commit Fase 4+3+7 con mensaje confirmado
2. Push + PR a `version-16`
3. ADRs candidatos identificados — tarea separada (no en este PR)

### No repetir
- No usar `cur_frm` en JS — Frappe v16 lo deprecó.
- Remote es `upstream` (no `origin`).
- No commitear en `version-16` directamente.
- `docs/referencia/` es generada — no editar manualmente.
- Tests Frappe requieren `bench run-tests`, no `pytest` directo.

---

## Decisiones vigentes

- Estado "Ganada" es un workflow state real — transición "Marcar como Ganada" desde "Enviada al Cliente"
- Botón "Crear Proyecto" requiere docstatus=1 Y workflow_state="Ganada"
- Botón "Sales Order" requiere "Ganada" Y proposal_project set
- Submit automático ocurre en la transición Borrador → En Revision (doc_status=1 en fixture)
- `assert_can_manage_proposals()` permite System Manager + Proposals Manager
- Idempotencia en project.py — no verifica proposal_project en el guard
- `docs/referencia/` generada con `python3 scripts/generate_reference.py`
- Custom fields en Quotation no aparecen en referencia/doctypes.md (están en fixtures/)

---

## Archivos relevantes ahora

### Leer primero
- `facturacion_mexico/working_docs/active/PLAN_MKDOCS_SETUP_ECOSISTEMA.md`

### Probablemente editar (ADRs — tarea posterior)
- `docs/adr/` — 3 candidatos: idempotencia proyecto, permission guards, submit automático

### No tocar
- `docs/referencia/` — generado, no editar manualmente
- `version-16` directamente

---

## Riesgos / cuidados

- ADRs candidatos identificados pero NO incluidos en este PR — pendiente commit posterior
- Anchor links INFO en referencia/api.md preexistentes — no bloquean build
- frappe-multisite necesita puerto 8767 para docs de erpnext_proposals — pendiente al finalizar PR
