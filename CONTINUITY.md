# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-12
**Rama activa:** `feat/project-authorized-economics` (base `upstream/version-16` = v0.22.1; versión objetivo **0.23.0**)
**Tarea actual:** Contrato económico canónico Project ↔ Quotations (ADR-0020) — en ciclo `/ship`, detener en PR.

---

## Recuperación rápida

Estoy trabajando en:
El **contrato económico** de `erpnext_proposals`: autorizado vigente de un Project = Original(root) +
Σ(addendas aplicadas), y sincronización de `Project.estimated_costing`. `pmo` es consumidor posterior,
nunca dependencia.

Plan que estoy siguiendo:
Diseño cerrado por el usuario + ADR-0020.

Objetivo inmediato:
Cerrar `/ship` hasta **PR** contra `version-16` (sin merge, sin tag/Release).

Criterio de avance:
PR abierto con bump 0.23.0, CI en verde, alcance limitado al contrato económico.

---

## Estado actual

### Ya cerrado
- `utils/project_economics.py` (nuevo): `get_project_authorized_economics` + `sync_project_authorized_cost`.
- Integración en `create_project_from_quotation` (post-materialize, pre-commit) y `apply_addendum_to_project`
  (post-asociación, sin commit interno). **Opción A**: `apply_addendum` solo acepta addendas `ROOT-ADD-NN`.
- Guard canónico único `quotation.assert_economic_snapshot_complete` reusado por `before_submit`, transiciones
  de workflow (excluida Borrador→En Revisión) y el contrato económico. Gate por `proposal_template`.
- Fix `rate_locked=1` conserva `costing_rate=0` en `economic_calendar._labor_rate_source` **y**
  `profitability_estimate`.
- Tests: `test_project_economics.py` (18) + `test_apply_addendum.py` reescrito (12). Suite 698/699.
- Docs: ADR-0020, CHANGELOG, arquitectura, mkdocs nav. Bump 0.22.1 → 0.23.0.

### Pendiente inmediato
1. `/ship` commit → push → PR contra `version-16`. **Detener en PR.**

### No repetir
- No volver a cambiar la versión (0.23.0).
- No reimplementar fórmulas económicas: fuente única = motor (`_evaluate_doc`).
- No tocar `pmo`. No `set_value` con `save()` para `estimated_costing` (usar `update_modified=False`).
- No intentar corregir `test_09b` (#60, ambiental local; pasa en CI).

---

## Decisiones vigentes
- Modelo `1 Project = 1 raíz + N addendas`; raíz resuelta por `proposal_project` (nunca por nombre).
- `estimated_costing` = espejo derivado idempotente (fuente histórica = Quotations congeladas).
- Invariante de congelamiento **validado** (fail-closed), no asumido. Moneda v1 fail-closed sin FX.
- La sync usa `_evaluate_doc` (núcleo) por permisos: la derivación es de sistema (autoridad = WRITE Project),
  no lectura de Quotations del usuario operativo.

---

## Archivos relevantes ahora
### Leer primero
- `erpnext_proposals/erpnext_proposals/utils/project_economics.py`
- `docs/adr/0020-contrato-economico-project.md`
### No tocar
- Motor económico (`_evaluate_doc`), `pmo`, private pack.

---

## Riesgos / cuidados
- `test_09b` (#60) falla solo local por `Selling Settings.allow_multiple_items=1`; pasa en CI.

## Información faltante
- Ninguna para cerrar el PR. Consumo real desde `pmo` (Autorizado→Ordenado→Facturado) es trabajo posterior.
