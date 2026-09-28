# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-28
**Rama activa:** `feat/rentabilidad-ux-fuente-costo` (base `upstream/version-16` = v0.30.2 → objetivo **v0.31.0**)
**Tarea actual:** PR — UX de trazabilidad de la fuente del costo en el Print Format `Rentabilidad Estimada`.

---

## Recuperación rápida

Estoy trabajando en:
Mejora de PRESENTACIÓN del Print Format `Rentabilidad Estimada` (rentabilidad PREVISTA). El motor
económico queda **sin cambios**. Usa datos que el read-model ya expone (`external_source` por línea).

Plan que estoy siguiendo:
Un cambio de PF + tests + doc (commit `7dd6458`) + bump MINOR a v0.31.0 (feat) + CONTINUITY. PR hacia `version-16`.

Objetivo inmediato:
Dejar el PR listo para merge (el merge lo hace el usuario).

Criterio de avance:
Suite completa **824 OK**; ruff OK; `mkdocs build --strict` OK; PF activo se actualiza con `bench migrate`
(no es PF histórico — el candado ADR-0011 rastrea el PF comercial, no la Rentabilidad Estimada).

---

## Estado actual

### Ya cerrado (esta rama)
- **UX Rentabilidad (commit `7dd6458`):** `rentabilidad_estimada.json` (fuente del costo vía `srclabel`,
  $0 válido vs `sin_costo`, warnings por línea, columna Fuente en Required, terminología "Mano de obra
  interna"/"Costos externos"); `tests/test_rentabilidad_ux.py` (6 tests); `docs/usuario/evaluacion-economica.md`.
- **Bump v0.31.0** (MINOR, feat) + CONTINUITY.

### Pendiente inmediato
1. Gate `pr-ready` → push + PR (autorizado por invocación de `/ship pr`).
2. Merge: **lo ejecuta el usuario** (no autorizado a Claude en este ciclo).
3. Tras merge: `/sync-check` + `/ship release` (tag/Release v0.31.0).

### No repetir / atención
- Motor económico intacto: no tocar `economic_calendar`/`item_cost`/`resolve_external_cost`.
- Auditoría de recurrencia/modalidades/handoff: analizada en conversación; **sin implementación** (fuera de este PR).
- **#41:** abierto, sin implementación.

## Decisiones vigentes
- El cambio es exclusivamente de presentación del PF (previsto), sin cambios de motor ni de metadata.

## Información faltante
- Ninguna para el PR.
