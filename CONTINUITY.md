# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-08-30
**Rama activa:** `fix/gotenberg-render-cover-toolbar` (base `upstream/version-16` = **v0.11.1**)
**Tarea actual:** Cerrar el fix público **v0.11.2** — el renderer Gotenberg respeta print-media y los márgenes del Print Format. Commit hecho; falta push + PR.

---

## Recuperación rápida

Estoy trabajando en:
Adopción de Gotenberg para el pack Actiglobal. La validación visual del PF real (Bolsa de Horas v3,
gotenberg-v1) destapó defectos del **renderer genérico** (no del pack), que v0.11.2 corrige.

Plan que estoy siguiendo:
Flujo `/ship` de v0.11.2: commit ✓ → push → pr (base `version-16`). Tras merge: `/sync-check` → `/ship release`.

Objetivo inmediato:
`/ship push` de `fix/gotenberg-render-cover-toolbar` → `/ship pr`. Luego **retomar el pack 1.7.0**
(sellar `releases/1.7.0/` + `MANIFEST.sha256`) — el pack NO va por Git, es file-based.

Criterio de avance:
Suite completa verde (368 OK); PDF real aprobado por el usuario (18 pág, sin solape).

---

## Estado actual

### Ya cerrado
- **v0.11.0** (ADR-0015): renderer PDF desacoplado. **v0.11.1**: loader puede sembrar
  `proposal_renderer_profile`. Ambos released (tag + GitHub Release alineados).
- **Pack 1.7.0 aplicado en LOCAL** (`proposals-acti.dev`): PF `Bolsa de Horas - Consultoría Microsoft v3`
  con `gotenberg-v1`, v2 disabled, Template→v3. Idempotente. **NO sellado todavía.**
- **v0.11.2 implementado** (esta rama): renderer Gotenberg corregido y **aprobado visualmente** por el
  usuario contra el original del cliente.

### En progreso
- `/ship` de `fix/gotenberg-render-cover-toolbar` (commit hecho; falta push + PR).

### Pendiente inmediato
1. `/ship push` + `/ship pr` de v0.11.2 (base `version-16`). Tras merge: `/sync-check` → `/ship release`.
2. **Pack 1.7.0**: sellar `releases/1.7.0/` + `MANIFEST.sha256` (file-based, NO Git). Validación ya hecha local.

### No repetir
- El pack Actiglobal **NO va por Git ni `/ship`**: control file-based (SemVer del catálogo + MANIFEST + releases/).
- NO tocar v1/v2 (históricos) ni el Letter Head compartido; NO staging/producción.
- El PF real usa assets por `{{ base_url }}/files/...` (http): v1/v2 legacy NO renderizan sin el dev server arriba.
- `bench console`: rutas absolutas en `exec(open(...))`.

---

## Decisiones vigentes (v0.11.2 — renderer Gotenberg)
- **Normalización PDF:** quita `.print-hide` (toolbar printview) y `.hidden-pdf`; revela `.visible-pdf`.
  Se aplica a portada y cuerpo.
- **Portada:** `#header-html` se descarta; `#footer-html` se envía como `footer.html` (footer al pie).
- **Márgenes:** se leen del CSS `.print-format` del formato (misma fuente que wkhtmltopdf, last-wins) y
  se convierten a pulgadas para Gotenberg → header/footer en su reserva contractual, sin hardcodear.
  Body y cover con sus márgenes; portada full-bleed (top/left/right=0).
- Body conserva header/footer repetidos; legacy intacto.

---

## Archivos relevantes ahora

### Leer primero
- `erpnext_proposals/utils/renderer.py` — `read_print_format_margins`, `body/cover_page_options(html)`,
  `normalize_html_for_pdf`, `render_proposal_pdf_gotenberg`.

### Probablemente editar (fase pack, después de v0.11.2)
- Pack `erpnext_proposals_catalog/`: sellar `releases/1.7.0/` + `MANIFEST.sha256`.

### No tocar
- Pack Actiglobal en Git (es file-based). v1/v2, Letter Head compartido. `one_offs/` (ignorado).

---

## Riesgos / cuidados
- El PDF real de revisión queda en `/home/erpnext/Descargas/` y `/tmp/` (`..._REVISION2.pdf`).
- Dev server de `proposals-acti.dev` (8410) quedó arriba (levantado para el A/B legacy).

---

## Información faltante
- Ninguna para continuar el `/ship` de v0.11.2.
