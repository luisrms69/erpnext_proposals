# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-05-30
**Rama activa:** `docs/mkdocs-standard-fase1-fase2`
**Tarea actual:** Fase 1 + Fase 2 de estructura MkDocs estándar — pendiente commit

---

## Recuperación rápida

Estoy trabajando en:
Implementación del estándar documental MkDocs del ecosistema en erpnext_proposals.
Fase 1 (estructura limpia) y Fase 2 (generador de referencia) completadas y listas para commit.

Plan que estoy siguiendo:
`facturacion_mexico/working_docs/active/PLAN_MKDOCS_SETUP_ECOSISTEMA.md`

Objetivo inmediato:
Commit de Fase 1 + Fase 2, luego PR a `version-16`.

Criterio de avance:
Commit creado, `mkdocs build --strict` limpio, PR abierto.

---

## Estado actual

### Ya cerrado
- PR #23 — permission guards, role fixture, project idempotency fix
- PR #22 — project guard, SO button, default project name
- Diagnóstico completo de erpnext_proposals contra el procedimiento piloto

### En progreso
- Rama `docs/mkdocs-standard-fase1-fase2` — listo para commit

### Pendiente inmediato
1. Commit con mensaje ya confirmado
2. Push + PR a `version-16`
3. Fase 3 + 4 + 7 (segundo PR): escribir `arquitectura.md`, `setup.md`, verificar usuario/

### No repetir
- No usar `cur_frm` en JS — Frappe v16 lo deprecó.
- Remote es `upstream` (no `origin`).
- No commitear en `version-16` directamente.
- CONTINUITY.md se actualiza con `/update-continuity`, nunca manualmente.
- `docs/referencia/` es generada — no editar manualmente.

---

## Decisiones vigentes

- `visual-regression/` PDFs → `working_docs/archive/visual-regression/` (evidencia histórica)
- READMEs de visual-regression → consolidados en `docs/tecnico/print-formats.md`
- `scripts/generate_reference.py` copiado de facturacion_mexico, idempotente
- Anchor links INFO en referencia/api.md no bloquean el build — deuda del generador, existe en facturacion_mexico también
- No se usa `_quarantine/` en erpnext_proposals — docs/ estaba limpia
- `assert_can_manage_proposals()` permite System Manager + Proposals Manager
- `assert_can_create_project` NO verifica `proposal_project` — idempotencia en `project.py`

---

## Archivos relevantes ahora

### Leer primero
- `facturacion_mexico/working_docs/active/PLAN_MKDOCS_SETUP_ECOSISTEMA.md` — procedimiento completo
- `mkdocs.yml` — nav actualizado con referencia/ y print-formats

### Probablemente editar (Fase 3+4+7)
- `docs/tecnico/index.md` — reemplazar placeholder por índice real
- `docs/tecnico/arquitectura.md` — crear desde template
- `docs/tecnico/setup.md` — crear con entorno real
- `docs/usuario/*.md` — verificar 8 páginas contra código real

### No tocar
- `docs/referencia/` — generado, no editar manualmente
- `version-16` directamente

---

## Riesgos / cuidados

- Fase 7 debe verificar `propuesta-ganada.md` y `proyecto-generado.md` contra `project.py`
  — ese flujo tuvo un bug corregido en PR #22/#23 (idempotencia segundo clic)
- ADR candidatos de PR #22/#23 identificados pero no convertidos — no en este PR
- Custom fields en Quotation no aparecen como DocType propio en referencia/doctypes.md
  — viven en fixtures/custom_field.json
