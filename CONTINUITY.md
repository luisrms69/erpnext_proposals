# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-26
**Rama activa:** `fix/issue-60-change-settings` (base `upstream/version-16` = v0.30.1 → objetivo **v0.30.2**)
**Tarea actual:** PR — aislamiento hermético del test de #60 (`change_settings` nativo).

---

## Recuperación rápida

Estoy trabajando en:
Entregar exclusivamente el cambio de **issue #60**: `test_09b_duplicate_item_line_rejected_by_erpnext`
fuerza `Selling Settings.allow_multiple_items = 0` con el mecanismo NATIVO `frappe.tests.change_settings`
(el mismo que usa ERPNext), que restaura el valor previo al salir. Elimina el `SkipTest` anterior.

Plan que estoy siguiendo:
Un único cambio de test (commit `26c5963`) + bump PATCH a v0.30.2. PR hacia `version-16`.

Objetivo inmediato:
Dejar el PR listo para merge (el merge lo hace el usuario).

Criterio de avance:
Suite completa **818 OK / 1 skip**; `allow_multiple_items` restaurado tras la corrida; ruff OK.

---

## Estado actual

### Ya cerrado (esta rama)
- **#60 (commit `26c5963`):** `tests/test_scope_catalog_resync.py` — `test_09b` usa `change_settings`
  (import `from frappe.tests import change_settings`); sin cambios de código productivo.

### Pendiente inmediato
1. Gate `pr-ready` → push + PR (autorizado).
2. Merge: **lo ejecuta el usuario** (no autorizado a Claude en este ciclo).
3. Tras merge (fuera de este ciclo): `/sync-check` + `/ship release` (tag/Release v0.30.2).

### No repetir / atención
- **#62:** auditoría cerrada (issue CLOSED), sin cambios de código.
- **#41:** solo investigación; **abierto, sin implementación**; NO cerrar, NO implementar el vaciado de
  `tc_name`/`terms` estudiado.
- La rentabilidad se auditará en una conversación posterior (no en este ciclo).

## Decisiones vigentes
- El cambio de #60 es exclusivamente de test (hermeticidad FX del setting vía mecanismo nativo).

## Información faltante
- Ninguna para el PR.
