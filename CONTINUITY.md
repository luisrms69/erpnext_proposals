# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-08-27
**Rama activa:** `feat/proposal-rendering-infrastructure` (base `upstream/version-16` = **v0.9.1**)
**Tarea actual:** Cerrar por `/ship` la feature pública **v0.10.0** (infraestructura genérica de render de propuestas). Commit feature + fix de fixture-filter hechos; siguiente: re-ejecutar `/ship pr`.

---

## Recuperación rápida

Estoy trabajando en:
El versionado/PR del app PÚBLICO `erpnext_proposals`. Feature genérica, backward-compatible, sin
hardcodes de cliente: Letter Head explícito por plantilla + portada separada opcional (2 renders +
merge pypdf) + helpers de paginación/numeración + campos de servicio en Item + loader v9.

Plan que estoy siguiendo:
Flujo `/ship`: commit (hecho) → push → pr. Bump 0.9.1 → 0.10.0 (MINOR). PR base `version-16`.
Un solo PR "infraestructura genérica de propuestas" (decidido con el usuario; incluye los 3 campos de Item).

Objetivo inmediato:
`/ship push` de `feat/proposal-rendering-infrastructure` y luego `/ship pr` hacia `version-16`.

Criterio de avance:
Push OK con upstream configurado; PR abierto con descripción GENÉRICA (no cliente) y gates de
versionado/documental de `/ship pr` en verde. Cada paso con autorización explícita separada; git solo
vía `/ship` [[feedback_git_solo_via_ship]]; nunca merge — lo hace el usuario [[feedback_nunca_merge]].

---

## Estado actual

### Ya cerrado
- **Commit de la feature** en la rama de trabajo (bump 0.10.0 incluido). 9 archivos de código + 6 de docs.
- **Fix `hooks.py`:** agregados los 3 fieldnames de servicio de Item al allowlist del filtro de fixtures
  (`test_fixture_hooks_consistency` lo exigía; patrón `fixture-patterns`). Ver [[feedback_fixture_filter_hooks]].
- **Fix test `SNAP_KEYS`:** agregado `page_break_before` al set de estructura exacta del snapshot
  (`_build_sections_snapshot` ya lo congela; `test_sections_snapshot.test_01` lo exigía).
- **Fix hermeticidad CI (PR #47):** `test_proposal_specific_scope` y `test_scope_moment_snapshot` creaban
  Quotations sin `selling_price_list` y dependían del default de Selling Settings (presente en local, ausente
  en el site fresco de CI `--lightmode`) → `save/submit` fallaba con MandatoryError. Fix: reutilizar
  `get_test_price_list()` (patrón hermético ya vigente). **Suite completa 327 tests: 0 failures / 0 errors.**
  Ver [[feedback_test_hermeticidad_price_list]].
- Documentación: ADR-0014 (render portada separada + merge), `tecnico/print-formats.md`, `tecnico/arquitectura.md`,
  `usuario/campos-principales.md`, `CHANGELOG 0.10.0`, `mkdocs.yml`. `mkdocs build --strict` limpio.
- Validación visual del candidato en un site de desarrollo (18 págs): portada full-bleed 1 pág sin header,
  header en 17/17 interiores, footer 18/18, sin recortes, sin huérfanos, tabla 5.3 y firmas OK.
- Regresión verde: print_format_integrity(19)/print_format_versions(4)/get_sections_snapshot(18)/
  phase_tags_loader(5). Idempotencia loader 0/0/0. ruff check+format limpios.

### En progreso
- `/ship push` pendiente de autorización explícita del usuario.

### Pendiente inmediato
1. `/ship push` (verificar/configurar upstream HTTPS + push de la rama).
2. `/ship pr` → PR hacia `version-16` (describir la capacidad GENÉRICA, no la implementación de cliente).
3. Post-merge (usuario mergea, nunca Claude): `/sync-check` + `/ship release` (tag+Release **v0.10.0**).

### No repetir
- NO intentar header repetible con `#header-html` dentro del Print Format custom ni `position:fixed`:
  ambos fallan en wkhtmltopdf (fuera de página / no repite). Solución = 2 renders + merge (ADR-0014).
- NO incluir el pack privado del cliente en este PR (catálogo, Print Format brandeado, script de build,
  assets): vive fuera del repo, en una ruta privada externa (ADR-0006). El repo público es solo genérico.
- NO commitear en `version-16` (rama protegida). NO desplegar staging ni transferir/release del pack todavía.

---

## Decisiones vigentes
- **Portada separada + merge (ADR-0014):** opt-in por `Proposal Template.separate_cover_page`; el modo va
  por `doc.proposal_render_part` ('cover'|'body'); merge con pypdf; fallback single-render. Sin tocar core,
  sin monkey-patch, sin afectar otros Print Formats.
- **Letter Head explícito por nombre:** `Proposal Template.letter_head → Quotation.letter_head`; el loader
  siembra Letter Heads con `is_default=0` (nunca default del sitio).
- **Anti-huérfanos:** `keep_headings_with_next` usa `page-break-inside:avoid` + `overflow:hidden` (wkhtmltopdf
  ignora `page-break-after:avoid`). Ver [[reference_separate_cover_2render]].
- App genérica en el repo; branding/catálogos reales en packs privados por ruta externa (ADR-0006)
  [[reference_clientes_packs_sites]].

---

## Archivos relevantes ahora

### Leer primero
- `docs/adr/0014-render-portada-separada-merge.md` — la decisión de arquitectura.
- `erpnext_proposals/erpnext_proposals/utils/print_format.py` — `render_proposal_pdf`, `sync_letter_head_from_template`, `_uses_separate_cover`.

### Probablemente editar
- Solo si CI/CodeRabbit piden ajustes; irían en esta misma rama.

### No tocar
- `version-16` (protegida). El pack privado fuera del repo.

---

## Riesgos / cuidados
- El "fantasma" invisible del heading tras el footer se resolvió con `overflow:hidden`; si se toca la CSS de
  `.keep-with-next`, revalidar que no reaparezca.
- Preflight de staging aprobado (wkhtmltopdf 0.12.6.1 patched qt, pypdf 6.13.3, header/footer 3/3, PDF real
  desde producción). NO desplegar staging ni transferir el pack todavía.

---

## Información faltante
- Confirmar el remoto `upstream` HTTPS del app público antes de `/ship push` (`git remote -v`; si falta,
  seguir el flujo `gh` HTTPS autorizado del CLAUDE.md del bench).
