# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-10-13
**Rama activa:** `fix/parent-task-date-rollup` (base `upstream/version-16` = v0.36.1 → objetivo **v0.36.2**, PATCH)
**Tarea actual:** Fix de propagación de fechas a la Task padre-Item (defecto de staging PROJ-0091 tras v0.36.1).

---

## Recuperación rápida

La Task padre de un Item vendido sin Scope Items quedaba sin fecha de inicio pese a que su Task operativa
«Entregar» sí la tenía. Causa: las operativas no entraban a `_rollup_parent_dates` (no están en
`contracted`) y el rollup acoplaba inicio y fin. Fix en `project.py`: el rollup recibe todos los padres
materializados y lee las hijas persistidas en BD, fijando inicio y fin de forma independiente (hereda el
inicio aunque no haya fin; no inventa fin). No cambia la fecha del Project.

## Estado actual

### Hecho (en dev)
- `utils/project.py`: `_rollup_parent_dates(parent_task_names, project)` reescrito (lee hijas en BD,
  inicio/fin independientes, idempotente, respeta ediciones manuales de hojas); caller pasa
  `set(item_parent_by_row.values())`.
- Nuevo módulo de integración `tests/test_project_date_hierarchy.py` (8 casos: sin scope, multi, scope
  programado, scope sin programación, mezcla, idempotencia con edición manual, addenda, mismo Item ×3) —
  verifica `exp_start_date`/`exp_end_date` del **padre** y de la **hoja** en BD.
- **Suite completa: 823 OK (1 skip)**; ruff limpio.
- Bump `0.36.1 → 0.36.2`; CHANGELOG + CONTINUITY.

### Pendiente inmediato
1. `/ship pr` → push + PR a `version-16` con el bump 0.36.2 (autorizado).
2. **CI** valida. **El merge lo hace el usuario** tras CI verde.
3. Tras merge: `/sync-check` + `/ship release` (tag/Release v0.36.2) + limpieza de rama.

## Decisiones vigentes
- La fecha del padre-Item es un envelope **derivado** de sus hijas (se recalcula en cada corrida); las
  hojas (operativa/scope) preservan sus valores (la operativa se crea una vez; el scope viene de offsets).
- Colores de Tasks padre: siguen pendientes (decisión separada, fuera de alcance).
- No se migran proyectos históricos: el fix aplica al generar/reaplicar (idempotente).

## Información faltante / riesgos
- PROJ-0091 en staging se corrige al regenerarse (idempotente); sin corrección masiva.
