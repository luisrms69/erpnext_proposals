# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-10-05
**Rama activa:** `feat/remove-activity-type-costing` (base `upstream/version-16` = v0.33.0 → objetivo **v0.34.0**)
**Tarea actual:** PR — eliminación funcional de Activity Type del modelo de costeo.

---

## Recuperación rápida

Estoy trabajando en:
Retirar `Activity Type` como dimensión funcional. El costo laboral depende **solo de la Designation**:
`labor = horas × tarifa(Designation)`.

- `get_designation_cost(designation)` — ruta única Designation → Proposal Cost Matrix → `avg_costing_rate`.
- Proposal Cost Matrix: **una tarifa por Designation** (sin `activity_type` ni `is_general_rate`); `rebuild`
  agrega las fuentes HR por Designation y limpia filas legacy.
- Scope Item sin `default_activity_type`; Quotation Scope Item `activity_type` oculto y sin poblar
  (conservado solo por compatibilidad de snapshots históricos).
- Project/Task, reportes, PF comercial y Workspace sin Activity Type.
- Fingerprint de addenda: conservado como está (no se persiste; no reintroduce la dimensión).

Plan que estoy siguiendo:
Commit funcional (`e2f5af6`) + bump MINOR a v0.34.0 + CONTINUITY → push → PR hacia `version-16`.

Objetivo inmediato:
Dejar el PR listo para revisión/merge (el merge lo hace el usuario).

Criterio de avance:
Suite completa **835 OK (1 skipped)**; ruff + prettier + mkdocs `--strict` OK; migrate limpio; rebuild
verificado (8 Designations → 8 tarifas, 0 filas con activity_type, 0 duplicados).

---

## Estado actual

### Pendiente inmediato
1. Gate `pr-ready` → push + PR (autorizado por la invocación de `/ship`).
2. **Decisión de versión**: MINOR `0.34.0` (elegido, convención 0.x) vs MAJOR `1.0.0` (SemVer estricto por
   cambio incompatible). Override posible antes del merge.
3. Merge: **lo ejecuta el usuario** (`/ship merge`).
4. Tras merge: `/sync-check` + `/ship release` (tag/Release) + limpieza de rama.

### No repetir / atención
- Forward-only; históricos sin tocar (`costing_rate`/`rate_source` congelados intactos).
- `Quotation Scope Item.activity_type` y `Proposal Cost Matrix Log` conservan columnas legacy (audit); no
  se escriben ni se leen funcionalmente. Retiro físico futuro, opcional.
- Requiere `bench migrate` al instalar + `rebuild_cost_matrix` para poblar la tarifa por Designation.

## Decisiones vigentes
- Activity Type eliminado del costeo; tarifa única por Designation.
- Fingerprint de addenda conservado por compatibilidad histórica.

## Información faltante
- Confirmar nivel SemVer (MINOR vs MAJOR) antes del release.
