# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-14
**Rama activa:** `feat/addenda-change-control-v2` (base `upstream/version-16` = v0.23.0)
**Tarea actual:** Change Control v2 — **B1, B2 y B3 cerrados**. Fingerprint NO iniciado.

---

## Recuperación rápida

Estoy trabajando en:
Change Control v2 de `erpnext_proposals`. Bloque 0 documental cerrado (ADR-0019 §7); no se rediseña el
contrato. B1 (gate de venta neta), B2 (apply-split) y B3 (required_items al versionar) implementados.

Plan que estoy siguiendo:
Contratos B1/B2/B3 entregados por el usuario + ADR-0019 §7 / §7.1 / §7.4.

Objetivo inmediato:
B3 validado → commit + push en `feat/addenda-change-control-v2`. **No** PR, **no** tag/Release. Fingerprint NO.

Criterio de avance:
Commit real revisable por el usuario antes de autorizar el bloque siguiente (fingerprint).

---

## Estado actual

### Ya cerrado
- **B1** (`workflow_validations.py`): gate `net_total>0` solo para root; addenda `ROOT-ADD-NN` con `net_total==0`
  puede formalizarse. `tests/test_net_total_gate.py` (10). Commit `3b58830`.
- **B2** (`utils/project.py`, apply-split ADR-0019 §7.1): `apply_addendum_to_project` en 2 fases (Fase 1
  SIEMPRE asocia+sync; Fase 2 SOLO si hay scope ejecutable). `tests/test_apply_addendum.py` (18). Commit `fb49cd1`.
- **B3** (`utils/proposal_versioning.py`, ADR-0019 §7.4): `create_new_proposal_version` ahora copia
  `required_items` con `_copy_required_item(row)` — SOLO `item`/`qty`/`uom`/`auto_generated`, NUNCA los
  snapshots congelados (`frozen_cost_rate`, `frozen_cost_source`, `cost_locked`, `economic_behavior`,
  `billing_interval`, `billing_interval_count`). El freeze los repuebla al re-formalizar.
  `tests/test_proposal_versioning.py` +5 B3 (28 total).

### Pendiente inmediato
1. Fingerprint `get_addendum_delta_fingerprint` (NO iniciar sin autorización). Fuera de B3: fingerprint/
   hash/canonical JSON, guards de re-aprobación, `pmo`, nuevos campos/DocTypes, cambios de workflow.

### No repetir
- No copiar snapshots congelados de `required_items` al versionar (ocultaría un cambio de costo que el
  fingerprint deberá detectar). No usar `as_dict()` en `_copy_required_item`.
- `skip_scope_generation=True` retorna antes de `_autoload_required_items` → por eso se copian
  explícitamente y no se duplican.
- `test_09b_duplicate_item_line_rejected_by_erpnext` (#60) falla solo local (`allow_multiple_items=1`); pasa en CI.

---

## Decisiones vigentes
- Versionar preserva el INPUT semántico de `required_items`; el snapshot económico se recongela al volver a
  formalizar (captura el valor vigente). El fingerprint (bloque siguiente) detectará el delta.

---

## Archivos relevantes ahora
### Leer primero
- `erpnext_proposals/erpnext_proposals/utils/proposal_versioning.py` (`_copy_required_item`, `create_new_proposal_version`)
- `docs/adr/0019-aplicar-addendum-a-project-existente.md` (§7.4)
### No tocar
- freeze / `assert_economic_snapshot_complete` (B3 NO los cambia), `pmo`, `utils/addendum.py`.

---

## Riesgos / cuidados
- `test_09b` (#60) es la única falla de suite y es ambiental local (no del cambio).

## Información faltante
- Definición concreta del bloque de fingerprint (se recibirá tras revisar el commit de B3).
