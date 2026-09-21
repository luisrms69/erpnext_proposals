# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-20
**Rama activa:** `fix/legacy-economic-snapshot-repair` (base `upstream/version-16` = v0.25.1; objetivo **0.25.2**)
**Tarea actual:** Hotfix — reparación canónica de snapshots económicos LEGACY (compatibilidad histórica).

---

## Recuperación rápida

Estoy trabajando en:
Helper administrativo `utils/legacy_repair.repair_legacy_economic_snapshot(quotation_name, dry_run=True)` para
desbloquear Quotations históricas (pre-ADR-0017/0018) que fallan `assert_economic_snapshot_complete` al
avanzar workflow (Enviada→Ganada) o crear Project. Caso concreto en prod: SAL-QTN-2026-00001.

Plan que estoy siguiendo:
Diseño aprobado por el usuario (fail-closed, semántica legacy one_time/costo 0, sin datos vivos) + guard de
elegibilidad legacy por cutoff objetivo (creation de los Custom Fields del modelo económico en el site).

Objetivo inmediato:
`/ship` hasta PR + CI verde contra `version-16`. Detener ANTES del merge (el merge lo hace el usuario).

Criterio de avance:
8/8 tests del hotfix; suite 770/771 (única falla ambiental #60); CI verde.

---

## Estado actual

### Ya cerrado
- `repair_legacy_economic_snapshot`: fail-closed (existe, docstatus=1, proposal_template), no sobrescribe,
  aborta ante parcial/ambiguo y ante Scope costable sin rate_locked, re-valida con el guard canónico,
  persiste atómico (ORM db_set) + Comment de trazabilidad, dry_run por defecto, idempotente, solo por nombre.
- Guard de elegibilidad LEGACY: cutoff = MIN(creation) de `Quotation Item-proposal_cost_locked` /
  `proposal_economic_behavior`. creation < cutoff → elegible; posterior con snapshot vacío → aborta
  (posible corrupción). dry-run reporta creation/workflow_state/legacy_cutoff/legacy_eligible.
- Bump 0.25.2 + CHANGELOG. Tests: 8 casos (test_legacy_economic_repair).

### Pendiente inmediato
1. `/ship commit → push → pr → CI`. **Detener antes del merge** (lo hace el usuario en GitHub).
2. Después (separado): release 0.25.2 · desplegar solo erpnext_proposals a prod · dry-run del repair sobre
   SAL-QTN-2026-00001 · revisar · reparación real.

### No repetir
- El repair NO usa datos vivos (Item Price/last_purchase/Proposal Settings) ni hace backfill masivo.
- Solo repara docs demostrablemente pre-modelo (cutoff objetivo por Custom Field creation).
- `test_09b` (#60) falla solo local; pasa en CI.

---

## Archivos relevantes ahora
### Leer primero
- `erpnext_proposals/erpnext_proposals/utils/legacy_repair.py`
- `erpnext_proposals/erpnext_proposals/tests/test_legacy_economic_repair.py`

### No tocar
- Guard `assert_economic_snapshot_complete` (no se desactiva); producción; pack; fiscal.

---

## Decisiones vigentes
- Semántica legacy = one_time + costo externo 0 (`legacy_pre_economic_model`), equivalente al pasado.
- Elegibilidad legacy por cutoff objetivo per-site (creation de Custom Fields del modelo económico).

## Información faltante
- Ninguna para cerrar el PR. Merge/despliegue/repair real = pasos posteriores del usuario.
