# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-08
**Rama activa:** `fix/warn-costing-designation-rate` (base `upstream/version-16` = v0.22.0; versión objetivo **0.22.1**)
**Tarea actual:** Fix del warning de costeo — `Activity Type` opcional cuando hay tarifa general por Designation.

---

## Recuperación rápida

Estoy trabajando en:
Corrección de `_warn_non_blocking` para que el warning «costo laboral incompleto» use el mismo motor de
costeo (`get_designation_cost`) y **no** exija `Activity Type` cuando la Designation tiene tarifa general
válida en Proposal Cost Matrix.

Plan que estoy siguiendo:
Diagnóstico A1/A2 acordado en la sesión (el motor ya era correcto; solo el warning estaba desalineado).

Objetivo inmediato:
Cerrar el ciclo `/ship` hasta **PR** contra `version-16` (sin merge; el usuario revisa).

Criterio de avance:
PR abierto con bump 0.22.1, CI en verde, alcance limitado a `workflow_validations.py` + su test.

---

## Estado actual

### Ya cerrado
- `_warn_non_blocking` reescrito: usa `get_designation_cost`, evalúa filas vendibles **o** internas de costo,
  advierte solo cuando ninguna fuente resuelve tarifa (`sin_datos`). Sin tocar el motor de costeo.
- `tests/test_warn_costing_designation.py` (4 tests) — verde. Regresión: frozen_integrity 7, versioning 23,
  scope_item_generation 8 — OK. ruff limpio.
- Bump 0.22.0 → 0.22.1 + entrada CHANGELOG.

### Pendiente inmediato
1. `/ship` commit → push → PR contra `version-16`. **Detener en PR** (sin merge).

### No repetir
- No rellenar `Activity Type` para ocultar el problema (ese era el anti-patrón).
- No modificar `get_designation_cost` ni el motor de costeo (ya correcto).
- No tocar masters PMO reales, private pack ni datos DEMO.

---

## Decisiones vigentes
- El costo laboral se resuelve por Designation (tarifa general) sin requerir Activity Type; Activity Type
  es granularidad opcional. El warning quedó alineado con esa regla.
- Bug A2 (costo PMO 28,800 faltante en el demo de staging) era **dato** (fila PMO sin `designation` MANAGER PMO
  o sin tarifa DEMO 800), no código — se corrigió en la UI de la Quotation DEMO.

---

## Archivos relevantes ahora

### Leer primero
- `erpnext_proposals/erpnext_proposals/utils/workflow_validations.py` (`_warn_non_blocking`)
- `erpnext_proposals/erpnext_proposals/utils/cost_matrix.py` (`get_designation_cost`, sin cambios)

### No tocar
- Motor de costeo, masters PMO, private pack, catálogo/datos DEMO en staging.

---

## Riesgos / cuidados
- Escenario DEMO (un entorno de staging del cliente) es data sintética ZZ-DEMO, ajena a este PR.

## Información faltante
- Ninguna para cerrar el PR. Print format branded del cliente (consulta interrumpida) queda como tema aparte.
