# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-08-13
**Rama activa:** `feat/print-format-versioning-selector` (base `upstream/version-16` = **v0.8.0**).
**Tarea actual:** **Versionamiento operativo de Print Formats** — mecanismo genérico para operar Print Formats versionados sin modificar históricos (ADR-0011 intacto). (1) **Selector central** `get_proposal_print_formats` (whitelisted + `validate_and_sanitize_search_inputs`): criterio ÚNICO de elegibilidad `doc_type=Quotation` + `disabled=0`, reutilizado por `Quotation.proposal_print_format` y `Proposal Template.print_format` vía helper JS central (`public/js/proposal_print_format.js`, `app_include_js`). (2) **Validación de servidor change-aware** `assert_assignable_print_format(doc, fieldname)` en `validate` de Quotation y Proposal Template: bloquea ADOPTAR un formato no elegible pero **no** invalida referencias históricas no modificadas. (3) **Warning** en Proposal Template (`get_print_format_status`) si el `print_format` está disabled/inexistente/otro DocType — no reemplaza el valor. Sin renombrar formatos, sin formato paralelo, sin Custom Fields nuevos, sin tocar el selector estándar de impresión, sin resolución automática por familia. Convención de nombres documentada: `<Familia> — YYYY-MM-DD — Vn`. Tests **10/10**; suite **320 OK / 1 skip**; ruff + prettier@2.7.1 + `mkdocs --strict` limpios; `bench build` hecho.

**Ajuste ADR-0011 (mismo 0.9.0):** el modelo definitivo de históricos ya **no** exige reimpresión — el histórico oficial son los PDFs oficiales adjuntos del freeze. Se **retiró `disabled`** de `_PRESENTATION_FIELDS` del guard (`print_format_protection.py`): un Print Format histórico ahora puede pasar `disabled 0→1` por `doc.save()` (sin bypass); HTML/CSS/rename/delete siguen protegidos. ADR actualizado (Actualización 2026-08-12). **Loader v8** (`catalog_loader.py`): capacidad `print_format_versions` — deshabilita el anterior + adjunta changelog como `File` + repunta Proposal Templates, genérico e idempotente. Suite **325 OK / 1 skip**.

Versión: **0.9.0** ya en la rama (commits deff8d0 selector + 43e9166 bump). Este ajuste ADR-0011 va en el mismo 0.9.0 (no re-bump).

---

## Recuperación rápida

Estoy trabajando en:
`/ship commit` del ajuste ADR-0011 + loader v8 en `feat/print-format-versioning-selector`. Archivos: `utils/print_format_protection.py` (guard sin `disabled`), `docs/adr/0011-*.md`, `catalog_data/catalog_loader.py` (v8 `_seed_print_format_versions`), `tests/test_print_format_protection.py` (actualizado), `tests/test_print_format_versions.py` (nuevo).

Commit documental (mismo 0.9.0): nueva página de usuario `docs/usuario/versionar-print-formats.md`
(procedimiento operativo de versionamiento de Print Formats) + genericación de este `CONTINUITY.md`
(sin identificadores concretos de sitio/entorno).

Próximo paso concreto:
`/ship push` → `/ship pr` (base `version-16`) del app 0.9.0. Tras el merge: cierre post-merge + tag/Release `v0.9.0` (`/ship release`) + `/sync-check`. **Después** publicar el pack privado 1.23.0 (working ya listo: nuevo PF `Propuesta de Servicios Profesionales — 2026-08-12 — V1`, changelog, repunte de templates; `releases/1.22.0` intacta; MANIFEST 1.23.0 sin sellar). No desplegar prod sin mostrar `--check`/`--dry-run`.

Criterio de avance:
Cada paso con autorización explícita; nunca escritura en BD/servidores sin aviso. Git solo vía `/ship`.
[[feedback_git_solo_via_ship]] · nunca merge (lo hace el usuario) [[feedback_nunca_merge]].

---

## Estado actual

### Cerrado y publicado
- **PR #44** (`feat/resync-before-pdf-preview`) mergeado a `version-16` (squash `96f2abf`), **v0.8.0** tag+Release.
  Commits de la rama: `c915fe8` (resync antes de PDF), `c434741` (PDFs oficiales privados), `816d29a` (bump 0.8.0).
- **PR #43** (hardening + secciones opcionales, ADR-0011/0012/0013) — mergeado, v0.7.0.

### Pack privado de Consultoría (fuera del repo, file-based)
Sellado en **1.22.0** (`releases/1.22.0/`, MANIFEST regenerado, releases históricas intactas). Delta 1.21.0→1.22.0:
+29 Scope Items, +9 Phases, introducción reescrita (#3), "Quiénes somos" `integrando análisis` (#4),
y **#2 paginación**: `.service` sin `page-break-inside: avoid` en `propuesta_servicios_profesionales.css`
(quita el hueco antes de un servicio que no cabe). Aplicado y validado en el sitio de desarrollo (idempotente 0/0/0).
`Propuesta de Servicios Profesionales` es formato del pack (module Selling, no protegido); `Propuesta Comercial`
/ `Rentabilidad Estimada` son estándar de la app y PROTEGIDOS por el loader. Ver [[reference_clientes_packs_sites]].

### Diagnósticos entregados sin cambio de código (#5)
- Bloqueo transitorio "This form is not editable due to a Workflow." = estado cliente stale durante
  `frm.save()→reload_doc()` del resync; no es bug de datos. Sin corrección aplicada (no autorizada).

---

## Decisiones vigentes
- **Resync antes de PDF (solo en Borrador)** vive en el handler JS del botón; el **freeze (server) no resincroniza** —
  los PDFs oficiales conservan el contenido revisado. Test `test_15` lo blinda.
- **PDFs oficiales privados** (Comercial + Rentabilidad); lookup de reemplazo por prefijo + `attached_to` (privacy-agnóstico).
- **ADR-0011:** un Print Format usado por propuestas formalizadas (`proposal_effective_print_format`) es histórico e
  inmutable; para corregirlo en dev se limpió ese campo en 4 Quotations de prueba (opción B). En prod: no aplica sin decisión.
- **Snapshots de secciones:** cambiar el master `Proposal Section` no altera propuestas existentes hasta re-sync del
  snapshot (`_sync_sections_snapshot(force=True)` en Borrador). [[design_scope_resync_borrador]]
- App genérica en el repo; catálogos/branding/assets reales en el pack privado por ruta externa (ADR-0006).
- `facturacion_mexico` es `required_app`; el loader solo referencia masters fiscales, no los crea ni borra.

### No repetir
- No versionar contenido de cliente (branding, catálogos reales, assets, one_offs, PDFs). Gate de datos de cliente.
- No `git` manual — solo vía `/ship`. [[feedback_git_solo_via_ship]]
- **NUNCA** merge — lo hace el usuario. [[feedback_nunca_merge]]
- No confundir sitios/packs: cada cliente (p. ej. Consultoría, Acti) tiene su propio sitio de desarrollo y su pack privado; cuidado con la colisión de la serie `SAL-QTN` entre sitios. [[reference_clientes_packs_sites]]

---

## Pendientes (no implementados / no autorizados en repo público)
- #5 (flicker workflow) — solo diagnóstico; una corrección al flujo resync→reload sería un follow-up puntual si se autoriza.
- Pendientes funcionales previos aún abiertos (impuestos automáticos en Quotation, centro de costos obligatorio,
  reorganización Sections/Scope tipificados). No asumir resueltos.
- Versionamiento/registro formal del pack en su propio flujo file-based (ya sellado 1.22.0; despliegue a prod no hecho).

---

## Riesgos / cuidados
- Despliegue toca BD y servidores → autorización explícita en cada paso; servidores dev solo vía `frappe-multisite`.
- Transición de privacidad: propuestas ya congeladas con un comercial público existente conservan ese `File` hasta
  regenerarse; las nuevas quedan privadas desde el freeze.
- Requiere `bench build` (cambio de JS); no requiere `bench migrate` (sin esquema/fixtures).
