# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-14
**Rama activa:** `feat/addenda-change-control-v2` (base `upstream/version-16` = v0.23.0)
**Tarea actual:** Change Control v2 — **Bloque B1 cerrado** (gate de venta neta root vs addenda). B2 NO iniciado.

---

## Recuperación rápida

Estoy trabajando en:
Change Control v2 de `erpnext_proposals`. El Bloque 0 documental (ADR-0019 §7) ya está cerrado; no se
rediseña el contrato. B1 implementa el único cambio funcional del bloque.

Plan que estoy siguiendo:
Contrato B1 entregado por el usuario + ADR-0019 §7 (B0).

Objetivo inmediato:
B1 validado → commit + push en `feat/addenda-change-control-v2`. **No** PR, **no** tag/Release, **no** B2.

Criterio de avance:
Commit real revisable por el usuario antes de autorizar B2.

---

## Estado actual

### Ya cerrado (B1)
- `_validate_blocking` (transición Borrador→En Revisión): el gate `net_total>0` aplica **solo** a propuestas
  root (grupo normal). Una addenda canónica `ROOT-ADD-NN` puede formalizarse con `net_total==0`. Reutiliza
  `is_addendum_group()` (sin regex/parsing nuevo). `proposal_template` y `proposal_cost_center` siguen
  obligatorios para AMBOS. Sin gate alternativo de "contenido económico".
- `tests/test_net_total_gate.py` (nuevo): 10 tests (root 0 bloquea / root >0 pasa / addenda 0 pasa /
  addenda sin template|cost center bloquea, etc.). 10/10.

### Pendiente inmediato
1. B2 (NO iniciar sin autorización). Fuera de B1: apply-split, fingerprint, `required_items` al versionar, `pmo`.

### No repetir
- No introducir regex/parsing nuevo de addenda: usar `is_addendum_group()`.
- No relajar `proposal_template`/`proposal_cost_center` para addendas.
- No tocar freeze, `assert_economic_snapshot_complete`, workflow/estados, ni `utils/addendum.py`.
- `test_09b_duplicate_item_line_rejected_by_erpnext` (#60) falla solo local (`allow_multiple_items=1`); pasa en CI.

---

## Decisiones vigentes
- La distinción root vs addenda para el gate de venta neta se decide por `is_addendum_group(proposal_group)`
  (documentado en ADR-0019 §7.1 / línea 284).

---

## Archivos relevantes ahora
### Leer primero
- `erpnext_proposals/erpnext_proposals/utils/workflow_validations.py` (`_validate_blocking`)
- `docs/adr/0019-aplicar-addendum-a-project-existente.md` (§7)
### No tocar
- `utils/addendum.py`, freeze, `assert_economic_snapshot_complete`, `pmo`.

---

## Riesgos / cuidados
- `test_09b` (#60) es la única falla de suite y es ambiental local (no del cambio).

## Información faltante
- Definición concreta de B2 (se recibirá del usuario tras revisar el commit de B1).
