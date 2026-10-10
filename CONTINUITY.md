# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-10-06
**Rama activa:** `feat/project-item-parent` (base `upstream/version-16` = v0.34.1 → objetivo **v0.35.0**, MINOR)
**Tarea actual:** Rediseño de generación Project/Tasks — **una Task padre por Item** (ADR-0025).

---

## Recuperación rápida

Rediseño de `Quotation Ganada → Project/Tasks`: la materialización agrupa por **Item contratado** (una
Task `is_group=1` por ocurrencia de Item), con los Scope Items como hijas o una **Task operativa inicial**
(`"Entregar — <item>"`) cuando el Item no tiene alcance ejecutable. **Proposal Phase** deja de ser
obligatoria y de generar Tasks padre (queda como etiqueta/orden de presentación). Se retira
`default_commitment_scope_item` (reemplazado por la Task operativa). Idempotencia por el nuevo Custom Field
`Task.source_quotation_item_row` (padre `is_group=1` vs operativa `is_group=0`). Addendas con el mismo
criterio (trabajo nuevo → Tasks; económica-only → 0). PDF/Rentabilidad: por fase si todas tienen fase, por
Item si falta alguna. Compras y Control de Cambios sin cambios.

---

## Estado actual

### Hecho (en dev)
- Bloques 0,1,5 (núcleo + addendas), 4 (PDF/Rentabilidad) y 2 (retiro de `default_commitment_scope_item`).
- **Suite completa: 823 OK (1 skip)**; ruff limpio.
- `bench --site proposals.dev migrate` exitoso (actualización de sitio existente): nuevo Custom Field
  aplicado, DocField commitment fuera de meta, columna huérfana intacta (sin SQL).
- ADR-0025 + CHANGELOG + CONTINUITY actualizados.

### Pendiente inmediato
1. `/ship pr` → bump `0.34.1 → 0.35.0`, push y PR a `version-16`.
2. **CI** debe validar instalación limpia (`install-app` en sitio nuevo) + suite. **El merge lo hace el
   usuario** tras verificar CI.
3. Tras merge: `/sync-check` + `/ship release` (tag/Release v0.35.0) + limpieza de rama.
4. **No desplegar** en staging ni producción todavía.

## Decisiones vigentes
- Modelo por Item aprobado (ADR-0025). Fase opcional. Task operativa para Item sin alcance.
- Sin patch (quitar campo + añadir Custom Field no migra datos). Columna huérfana NULL, no se borra por SQL.
- Instalación nueva se valida por CI (no se creó sitio local; sin credenciales MySQL).

## Información faltante / riesgos
- Coexistencia temporal (aceptada) de proyectos históricos con padres-fase y nuevos con padres-Item; no se
  migran históricos.
