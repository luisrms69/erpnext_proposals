# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-08-30
**Rama activa:** `fix/loader-renderer-profile` (base `upstream/version-16` = **v0.11.0**)
**Tarea actual:** Fase de adopción de Gotenberg para el pack Actiglobal. **Paso 1 (en curso):** fix público **v0.11.1** — el loader ya puede sembrar `proposal_renderer_profile` desde el catálogo. Commit hecho; falta push + PR.

---

## Recuperación rápida

Estoy trabajando en:
Adoptar la capacidad Gotenberg (ADR-0015, v0.11.0) en el pack privado Actiglobal. Antes hay que
cerrar un fix público mínimo: el loader (`_seed_print_formats`) no incluía `proposal_renderer_profile`
en su allowlist, así que un catálogo no podía adoptar Gotenberg declarativamente.

Plan que estoy siguiendo:
1. **v0.11.1 (app público)** — allowlist `_PRINT_FORMAT_MANAGED_FIELDS` + `proposal_renderer_profile`,
   caps v10 (`renderer_profile`), test. Flujo `/ship`: commit ✓ → push → pr.
2. **Pack 1.7.0** — crear `Bolsa de Horas - Consultoría Microsoft v3` con `gotenberg-v1`, sin tocar v1/v2.

Objetivo inmediato:
`/ship push` de `fix/loader-renderer-profile` (autorización separada) → `/ship pr` (base `version-16`).

Criterio de avance:
Suite completa verde (357 OK); caps_version=10 y renderer_profile=True.

---

## Estado actual

### Ya cerrado
- **v0.11.0 released** (ADR-0015): renderer PDF desacoplado. Tag + GitHub Release alineados (8d3259f).
- **Fase 1 de adopción (inspección read-only del pack)** completa: pack en v1.6.1; template
  `Bolsa de Horas - Consultoría Microsoft` → PF `…v2`; assets por URL absoluta (incompatibles con
  header/footer Chromium); loader sin `proposal_renderer_profile` en allowlist (blocker).
- **v0.11.1 implementado** (commit en esta rama): fix del loader + caps v10 + 2 tests. Suite 357 OK.

### En progreso
- `/ship` de `fix/loader-renderer-profile` (commit hecho; falta push + PR).

### Pendiente inmediato
1. `/ship push` + `/ship pr` de v0.11.1 (base `version-16`). Tras merge: `/sync-check` → `/ship release`.
2. **Pack 1.7.0**: PF `…v3` (`gotenberg-v1`), `print_format_versions` (current=v3, supersedes=v2,
   disable + repunte de template), bump 1.6.1→1.7.0, sellar `releases/1.7.0/`. Validar visualmente local.

### No repetir
- NO tocar v1/v2 (históricos/operativos) ni el Letter Head compartido "Actiglobal — Propuestas".
- NO meter base64 gigante en el catálogo: v3 referencia assets como `/files/actiglobal_*.png`
  (relativos) y el adapter Gotenberg los inlinea a data-URI.
- NO desplegar el pack a staging/producción en esta fase (solo local `proposals-acti.dev`).
- `bench console` no corre desde bench root → rutas absolutas en `exec(open(...))`.

---

## Decisiones vigentes
- Blocker loader → **fix público** (no one_off): `proposal_renderer_profile` es capacidad genérica; el
  catálogo debe poder declararla. Tratado como **PATCH v0.11.1** (completa v0.11.0).
- v3 construye su **propio `#header-html`** con logo `/files/actiglobal_logo_color.png` relativo; el
  Letter Head histórico queda intacto (el Template conserva su metadata de letter_head).
- Bump del pack: **1.6.1 → 1.7.0 (MINOR)** por nueva versión de PF + adopción de capacidad.
- Nombre del nuevo PF: **`Bolsa de Horas - Consultoría Microsoft v3`**.

---

## Archivos relevantes ahora

### Leer primero
- `erpnext_proposals/catalog_data/catalog_loader.py` — `_PRINT_FORMAT_MANAGED_FIELDS`, `_seed_print_formats`, `_seed_print_format_versions`, `capabilities()`.
- Pack: `.../erpnext_proposals_catalog/actiglobal_catalog.json` (v1.6.1) — `print_formats`, `templates`, `print_format_versions`.

### Probablemente editar (Fase 2, pack)
- `actiglobal_catalog.json` (PF v3 + print_format_versions + version 1.7.0) + changelog + sellar `releases/1.7.0/`.

### No tocar
- PF `Bolsa de Horas - Consultoría Microsoft` (v1) y `… v2`; Letter Head "Actiglobal — Propuestas".
- `one_offs/` (ignorado).

---

## Riesgos / cuidados
- Assets en header/footer de Chromium: solo se inlinan rutas **relativas** (`/files/…`), no URLs
  absolutas (`base_url`/`get_url`). v3 debe usar relativas.
- Márgenes: `gotenberg-v1` usa defaults; el ajuste fino por formato es esperado (v2 por formato).

---

## Información faltante
- Ninguna para continuar el `/ship` de v0.11.1.
