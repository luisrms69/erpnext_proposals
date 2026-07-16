# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-07-15
**Rama activa:** `feat/proposal-phase-link`
**Tarea actual:** Convertir `phase` de texto libre a `Link(Proposal Phase)` en Scope Item y Quotation Scope Item. Implementado y validado; pendiente commit/PR.

---

## Recuperación rápida

Estoy trabajando en:
`phase` → Link a Proposal Phase. Orden por `Proposal Phase.sequence` (no alfabético) y display
`phase_name`, resuelto desde el catálogo sin campo duplicado. Corte limpio (sin patch/backfill).

Plan que estoy siguiendo:
Decisiones cerradas por el usuario (13 puntos) + ADR-0004. Fuera de alcance: manual_override,
backfill, orden de "Sin fase".

Objetivo inmediato:
`/ship commit` → `/ship push` → PR a `version-16` (autorizados).

Criterio de avance:
Suite 143 OK; validación funcional GUI en proposals-acti.dev (8 casos PASS); ADR + docs; PR verde.

---

## Estado actual

### Ya cerrado
- PR #26 (catálogo Proposal Phase), PR #28 (docs), PR #29 (resync #27, mergeado a version-16).
- **Esta rama:** `phase` Data→Link en 2 DocTypes; `utils/phase.py` (`phase_label`/`phase_sequence`/
  `order_phases`, jinja methods); consumidores actualizados (quotation, profitability, project,
  ambos Print Formats); tests (nuevo `test_phase_link.py` + helper `tests/phases.py` + actualizados
  immutability/resync/scope_item). ADR-0004. Docs + referencia regeneradas.
- Validación funcional server-side en proposals-acti.dev: 8 casos PASS (fase GUI, Link, generación,
  resync, orden por sequence, PDFs con phase_name, Project/Task). Docs de prueba `_GUITEST_*` limpiados.

### En progreso
- `/ship commit` → push → PR.

### Pendiente inmediato
1. Commit + push + PR de esta rama.
2. (Futuro, fuera de alcance) decidir si "Sin fase" debe ordenar al final; `manual_override`.

### No repetir
- **NUNCA** backfill/patch de datos históricos de fase (corte limpio; sitios nuevos configuran su catálogo).
- `bench migrate` **no recarga Print Formats** → tras migrar hay que `reload_doc(... force=True)`.
- El orden de fases usa `Proposal Phase.sequence`, no alfabético; "Sin fase" (sequence 0) va primero (heredado).
- `docs/referencia/` es autogenerada (`scripts/generate_reference.py`).
- Remoto es `upstream` (no `origin`). No commitear en `version-16`.

---

## Decisiones vigentes
- `phase` = Link; almacena `name`(=`phase_code`); display `phase_name`; orden por `sequence` (ADR-0004).
- Sin `phase_sequence` almacenado: se resuelve desde el catálogo en lectura.
- Despliegue: `bench migrate` + recargar Print Formats. Datos históricos con fase libre quedan como Links inválidos hasta ajuste manual.

---

## Archivos relevantes ahora

### Leer primero
- `utils/phase.py` — helpers de fase.
- `utils/quotation.py` (order_by), `report/profitability_estimate`, `utils/project.py` — consumidores.
- `print_format/*/*.json` — `phase_label`/`order_phases` en Jinja.
- `tests/test_phase_link.py`, `tests/phases.py`.

### No tocar
- `docs/referencia/` (generada). Orden de "Sin fase" (fuera de alcance).

---

## Riesgos / cuidados
- Cambio de esquema (fieldtype) — aplica con `bench migrate`; sin patch por decisión.
- `bench run-tests` solo en `test-erpnext_proposals.localhost`.
- proposals-acti.dev ya migrado a Link (sitio de pruebas).

---

## Información faltante
- Decisión UX: ¿"Sin fase" al final del orden? (fuera de alcance de este PR).
