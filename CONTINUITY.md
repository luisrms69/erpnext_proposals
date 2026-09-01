# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-01
**Rama activa:** `feat/loader-manage-scope-enabled` (base `upstream/version-16` = v0.12.0)
**Tarea actual:** Etapa **N:M Item ↔ Scope Item** lista para PR. Bump a **0.15.0** (MINOR; base 0.12.0 +
dos bumps previos que quedaron sin registrar en el CHANGELOG). El pack privado de cliente correspondiente
ya se validó y aplicó en su **sitio de staging** por el loader oficial (conteos N:M correctos, idempotente).
**PR #53** abierto contra `version-16` (https://github.com/luisrms69/erpnext_proposals/pull/53). Pendiente:
review/CI y **merge (lo ejecuta el usuario)**; luego cierre de release (tag + GitHub Release) — no en este ciclo.

---

## Recuperación rápida

Estoy trabajando en:
La relación **N:M entre Item y Scope Item** (un Scope Item puede aplicar a varios Items y viceversa),
vía child table `Scope Item.erpnext_items` (DocType `Scope Item ERPNext Item`) + resolver central
`resolve_scope_items_for_item` (une child + legacy `erpnext_item`, sin backfill). Este commit añade el
**soporte del loader de catálogos** (`"erpnext_items": [...]` por Scope Item) y la **documentación
completa** (usuario, arquitectura, ADR-0016, referencia regenerada).

Plan que estoy siguiendo:
1. `/ship commit` de loader + tests + docs — **HECHO** (ver "Último commit").
2. **Antes de push/PR:** aplicar el pack privado de cliente correspondiente en su **sitio de staging**
   y comprobar que cada Item del pack arrastra **solo su set** de Scope Items (aislamiento N:M).
3. Calcular el **bump SemVer** contra `upstream/version-16` (MINOR: nueva capacidad del loader +
   funcionalidad visible) e incluirlo antes del PR.
4. `/ship push` → `/ship pr` → release.

Objetivo inmediato:
Cerrar la validación del pack en staging antes de arrancar el ciclo largo push/PR. NO push/PR/deploy sin autorización.

Criterio de avance:
Tests N:M verdes; `mkdocs --strict` limpio; linters OK; aplicación real del pack en staging sin
`pending` y con sets correctos por Item.

---

## Modelo N:M (resumen)

- **Child table `Scope Item.erpnext_items`** (`Scope Item ERPNext Item`, campo único `item` Link→Item)
  = relación vigente. **Legacy `erpnext_item`** (Link único) se conserva **solo en lectura**.
- **Resolver único** `utils/scope_item_links.py:resolve_scope_items_for_item(item)` — une child+legacy,
  deduplica, opcional `enabled_only`. Todo el app resuelve por aquí.
- **UI:** botón *Scope Items* en el Item → `get/set_scope_items_for_item` (solo selecciona habilitados;
  aislamiento por Item al quitar).
- **Quotation:** el alcance se genera **solo para líneas de Item nuevas**; un guardado normal **no**
  repuebla; *Agregar Scope Items desde Items* recupera faltantes; *Sincronizar alcance desde catálogo*
  hace update+remove pero **no** repone.
- **Loader:** `"erpnext_items": [...]` por Scope Item — ausente=no toca, presente=sincroniza set,
  vacía=limpia; valida duplicados; Items inexistentes → `pending`.
- **Decisión permanente:** ADR-0016 (lectura-compatible, sin backfill ni patch).

---

## Validación del pack de cliente en staging (pendiente)

- El pack privado del cliente vive **fuera de este repo** (ubicación privada, nunca en git). No se
  commitea ningún dato ni identificador del cliente aquí.
- Flujo de validación: `dry_run=True` (precheck), luego aplicación real por el loader oficial en el
  **sitio de staging** del cliente, y validación por lectura de conteos N:M e idempotencia.
- **No aplicar** en ningún sitio sin autorización explícita (escribe en BD del sitio).

---

## Último commit

- `feat(loader): soporte N:M \`erpnext_items\` en catálogo + docs de la relación Item↔Scope Item`
- Loader + tests N:M + docs (usuario "Scope Items reutilizables", ADR-0016, arquitectura, crear-propuesta, referencia regenerada, nav).

---

## No repetir
- El resync **no** repone filas eliminadas — reponer es solo *Agregar Scope Items desde Items*.
- La generación de alcance solo aplica a **líneas de Item nuevas**, no en cada guardado.
- El loader **no** administra `enabled` del Scope Item (fuera de alcance).
- No hacer backfill/patch del legacy `erpnext_item`: el resolver los une en lectura.
- No aplicar packs de cliente en staging sin autorización explícita (escribe en BD).
- **Nunca** poner datos/identificadores de cliente en archivos trackeados del repo (incluido este).
