# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-11-27
**Rama activa:** `feat/scope-assignee-won-notification` (base `upstream/version-16` = v0.36.2 → objetivo **v0.37.0**, MINOR)
**Tarea actual:** Paquete v0.37.0 — periodicidad económica por línea, asignación automática de responsables + notificación post-Project, loader de catálogo caps v13, guard de centro de costos y fix de Project-on-Won en propuestas versionadas.

---

## Recuperación rápida

La rama agrupa el trabajo de varias pruebas funcionales sobre un sitio de desarrollo. Dos correcciones
críticas cierran la rama: (1) **centros de costos** — con el default de Company vacío, `cost_center` queda
obligatorio en los renglones de SO/PO/PI vía Property Setters (el sync de la propuesta lo llena desde el
Project antes de la validación); (2) **Project-on-Won en versiones** — las propuestas V2+ perdían
`source_row` al versionar (se excluía y la generación se omitía), lo que rompía `_item_parent_task` con
`MandatoryError: subject`; ahora se re-vincula en `validate` y `_item_parent_task` degrada con guard.

## Estado actual

### Hecho (en dev)
- `feat(economic)` 84bb7de — periodicidad genérica por línea + rentabilidad en moneda de cotización.
- `feat(project)` 839dbca — asignación automática configurable de responsables (Scope Item `default_assignee`
  + `operative_assignee_rules` por Item Group) y notificación encadenada tras crear el Project.
- `feat(catalog)` f9d9b46 — loader de catálogo caps v13 (reactivación controlada de categorías funcionales).
- `fix(cost-center)` 09150cc — `cost_center` reqd en Sales/Purchase Order Item y Purchase Invoice Item vía
  Property Setters (`fixtures/property_setter.json` + filtro en `hooks.py`). Config `Company.cost_center`
  vacía es específica del sitio (NO distribuida).
- `fix(project)` eda5f5e — `_relink_inherited_scope_source_rows` (re-vínculo de `source_row` en versiones) +
  guard en `_item_parent_task`; `tests/test_versioned_project_on_won.py` (V1/V2/source_row ausente).
- **Tests por impacto verdes:** Project-on-Won, versionado y generación de alcance (11 módulos, 121 tests) +
  `test_cost_center_guard` (5) + `test_item_proposal_fields` (13). Ruff limpio.
- Bump `0.36.2 → 0.37.0` (MINOR) + CONTINUITY.

### Pendiente inmediato
1. `/ship pr` → push + PR a `version-16` con el bump 0.37.0 (autorizado).
2. **CI** valida (atención al problema conocido MariaDB 10.6/TLS → usar MariaDB 11.8 si requiere corrección).
3. **El merge lo hace el usuario** tras CI verde (nunca Claude).
4. Tras merge: `/sync-check` + `/ship release` (tag/Release v0.37.0) + limpieza de rama.

## Decisiones vigentes
- `Company.cost_center` vacío es config de sitio, no va en fixtures ni en el commit; los guards validan que
  el CC exista por renglón, no que todos los renglones usen el mismo.
- El Print Format privado del cliente (`print_format/licenciamiento_microsoft/`) queda **untracked**: no
  se publica en el repo.
- En versiones, `source_row` se re-deriva contra las filas origen ACTUALES (nunca se reutilizan names
  obsoletos de la versión anterior); identidad por ocurrencia preservada.

## Información faltante / riesgos
- La periodicidad económica depende de metadata del Item (`proposal_economic_behavior`), que puebla un
  adaptador Microsoft en una app de customización del cliente; SKUs sin esa metadata se evalúan como
  `one_time` (no es defecto de esta rama; es dato de catálogo).
- Una propuesta de prueba quedó sin Project a propósito (no se regeneró); se materializará al reaplicar con el fix.
