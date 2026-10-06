# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-10-06
**Rama activa:** `hotfix/sidebar-card-break` (base `upstream/version-16` = v0.34.0 → objetivo **v0.34.1**)
**Tarea actual:** Hotfix — destrabar `bench migrate` en staging (fallo en `frappe.patches.v16_0.convert_sidebars`).

---

## Recuperación rápida

Estoy trabajando en:
Corregir el `Workspace Sidebar` de la app, que traía 4 ítems con `type="Card Break"` — valor inválido para
`Workspace Sidebar Item` (options: `Link/Section Break/Spacer/Sidebar Item Group`). El nuevo patch de Frappe
`convert_sidebars` (post_model_sync) reinserta esas filas en el nuevo `Sidebar Item` **validando** y aborta el
`bench migrate` de staging con `Row #2: Type cannot be "Card Break"`.

Cambio: las 4 filas (`Operacion`, `Configuracion de Propuestas`, `Reportes`, `Referencia`) pasan a
`type="Section Break"` y se les quita `link_to`/`link_type` (irrelevantes en un Section Break); se conserva
`label` y el resto. **No** se toca el Workspace normal (ahí `Card Break` es válido en `Workspace Link`).

Objetivo inmediato:
PR a `version-16` para desplegar el hotfix y destrabar staging (el merge lo hace el usuario).

Criterio de avance:
JSON válido; 0 `Card Break` en `workspace_sidebar/`; 4 `Card Break` intactos en el Workspace normal; diff
acotado al sidebar; migrate limpio en `proposals.dev`.

---

## Estado actual

### Pendiente inmediato
1. Push + PR a `version-16`.
2. Merge: **lo ejecuta el usuario** (`/ship merge`).
3. Tras merge: `/sync-check` + `/ship release` (tag/Release v0.34.1) + limpieza de rama.
4. **Desplegar en staging** la app actualizada **antes** de re-correr `bench migrate` (ver abajo).

### Orden de ejecución verificado (upstream version-16)
`convert_sidebars` está en `[post_model_sync]` → corre **después** de `sync_all()`, que re-importa este JSON
a la tabla viva `Workspace Sidebar` (con `ignore_validate=True`). `convert_sidebars` lee esa tabla viva
(`site_rows()` sobre `Workspace Sidebar`), no un snapshot. Por tanto: con la app corregida **desplegada antes**
del migrate, el sync deja `Section Break` y el patch no vuelve a fallar — **sin** intervención en BD.

### No repetir / atención
- Verificación local limitada: la frappe del bench es 16.33.1 y **no** incluye `convert_sidebars`; el migrate
  local valida JSON + sync, no el patch. Validación definitiva = staging (frappe más nueva).
- Gap upstream (independiente): `convert_sidebars` no normaliza `Card Break` (sí maneja `Spacer`/`Sidebar Item
  Group`). Candidato a reporte upstream; **no** se parchó core.

## Decisiones vigentes
- Hotfix PATCH `0.34.1` (fix compatible, sin nueva funcionalidad).
- Solución mínima: solo el JSON del sidebar; sin tocar core, BD, patches, hooks, otros sidebars ni PMO.

## Información faltante
- Confirmar el commit exacto de frappe en staging (asumido con la arquitectura nueva de sidebars).
