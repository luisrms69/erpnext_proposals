# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-14
**Rama activa:** `feat/addenda-change-control-v2` (base `upstream/version-16` = v0.23.0)
**Tarea actual:** Change Control v2 — **B1 y B2 cerrados**. B3 NO iniciado.

---

## Recuperación rápida

Estoy trabajando en:
Change Control v2 de `erpnext_proposals`. Bloque 0 documental cerrado (ADR-0019 §7); no se rediseña el
contrato. B1 (gate de venta neta) y B2 (apply-split) implementados.

Plan que estoy siguiendo:
Contratos B1/B2 entregados por el usuario + ADR-0019 §7 / §7.1.

Objetivo inmediato:
B2 validado → commit + push en `feat/addenda-change-control-v2`. **No** PR, **no** tag/Release, **no** B3.

Criterio de avance:
Commit real revisable por el usuario antes de autorizar B3.

---

## Estado actual

### Ya cerrado
- **B1** (`workflow_validations.py`): gate `net_total>0` solo para root (grupo normal); addenda `ROOT-ADD-NN`
  puede formalizarse con `net_total==0`. `tests/test_net_total_gate.py` (10). Commit `3b58830`.
- **B2** (`utils/project.py`, apply-split ADR-0019 §7.1): `apply_addendum_to_project` reordenado:
  - **Fase 1 — SIEMPRE:** asocia `proposal_project` → `sync_project_authorized_cost(project)`.
  - **Fase 2 — SOLO si hay scope ejecutable** (`include_in_proposal OR is_internal_cost_task`):
    `_validate_scope_for_project` + `_materialize_scope_into_project`. Sin scope ejecutable: 0 Tasks,
    devuelve dict con `scope_materialized=False`.
  - Sin commit interno; atomicidad por rollback de la transacción externa. `tests/test_apply_addendum.py`
    ampliado a 18 (6 nuevos B2: sin scope, solo Required, net_total 0, delta $0, idempotencia sin scope,
    y 2 de rollback ante fallo de sync / materialización).

### Pendiente inmediato
1. B3 (NO iniciar sin autorización). Fuera de B2: fingerprint `get_addendum_delta_fingerprint`, fix de
   `required_items` en `create_new_proposal_version`, `pmo`, nuevos campos/DocTypes, cambios de workflow.

### No repetir
- No reintroducir `_validate_scope_for_project` incondicional al inicio de `apply_addendum_to_project`
  (bloqueaba addendas económicas-only). El orden es: guards → Fase 1 → Fase 2 condicional.
- No relajar `proposal_template`/`proposal_cost_center` para addendas. No inventar Tasks.
- `test_09b_duplicate_item_line_rejected_by_erpnext` (#60) falla solo local (`allow_multiple_items=1`); pasa en CI.

---

## Decisiones vigentes
- Apply-split: la asociación se escribe ANTES del sync (el contrato económico identifica las addendas por
  `proposal_project==project`). La materialización corre DESPUÉS de la fase económica; un fallo en cualquier
  fase revierte todo con la transacción externa (sin commit interno).
- El test heredado `test_failure_mid_materialization_no_association` se migró a
  `test_failure_during_materialization_rolls_back` (modelo de rollback), porque el nuevo orden asocia antes
  de materializar. Cambio dirigido por el contrato B2, no para ocultar un fallo.

---

## Archivos relevantes ahora
### Leer primero
- `erpnext_proposals/erpnext_proposals/utils/project.py` (`apply_addendum_to_project`)
- `docs/adr/0019-aplicar-addendum-a-project-existente.md` (§7.1)
### No tocar
- `utils/addendum.py`, freeze, `assert_economic_snapshot_complete`, `pmo`.

---

## Riesgos / cuidados
- `test_09b` (#60) es la única falla de suite y es ambiental local (no del cambio).

## Información faltante
- Definición concreta de B3 (se recibirá del usuario tras revisar el commit de B2).
