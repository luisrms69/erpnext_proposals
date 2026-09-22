# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-22
**Rama activa:** `refactor/loader-drop-desk-managed-seeders` (base `upstream/version-16` = v0.27.0; objetivo **0.28.0**)
**Tarea actual:** Depuración de fuentes de verdad — el loader del pack deja de sembrar los maestros funcionales (ahora en Desk). Ver **ADR-0023**.

---

## Recuperación rápida

Estoy trabajando en:
El loader de catálogos (`catalog_data/catalog_loader.py`) sembraba maestros funcionales que los usuarios
administran en Desk (Templates, Scope Items, Phases, registro/flags de Item, Payment Terms, Designations,
Skills, `economic_behavior_rules`) → segunda fuente de verdad + conflictos. Se depura a **caps v12** para
conservar SOLO la capa editorial/de presentación.

Plan que estoy siguiendo:
Retirar esos seeders del loader + trimear `_CLEARABLE_TYPES`; `_seed_items` pasa a editorial-only y **nunca
crea Items** (Item ausente → `pending`); `capabilities()` añade `no_functional_master_writes` y retira las
capacidades muertas. Depurar los DOS packs reales (catálogos → v2.0.0, solo capa editorial) + ajustar
instalador/normalizer/docs/manifest de Pack A. Sin borrar datos de BD. No nuevos mecanismos de migración.

Objetivo inmediato:
Commit de este bloque (hecho, sin push por indicación del usuario) → revisión del usuario → luego push/PR.

Criterio de avance:
Suite completa 787 OK / 1 skip; ruff clean; mkdocs strict OK; ambos packs cargan en dry-run sin errores
(Pack B 0 conflictos; Pack A solo el conflicto pre-existente de PF histórico, ADR-0011). Backup PRE-LIMPIEZA intacto.

---

## Estado actual

### Ya cerrado (esta rama) — lado app (git)
- `catalog_data/catalog_loader.py`: retirados seeders de phases/tags, scope_items(+deps/n2m), templates,
  economic_behavior_rules, payment_terms(+templates), skills, designations, y sus helpers/`_require`.
  `_seed_items` → editorial-only, no crea Items. `_CLEARABLE_TYPES` = sections/items/letter_heads.
  `capabilities()` v12 + `no_functional_master_writes`. `_seed_print_format_versions` intacto (dormido: los
  catálogos ya no traen `templates`).
- `catalog_data/sample_catalog.json`: solo `sections` (+versioned), v1.1.0.
- Tests: eliminados `test_phase_tags_loader` / `test_scope_pmo_catalog` / `test_designations_skills`;
  reescritos `test_catalog_loader` (re-basado en editorial + regresión de ausencia de seeders) y
  `test_catalog_clear_fields` (sobre Item editorial); ajustado `test_item_proposal_fields` (Item precreado).
- Bump 0.28.0 + CHANGELOG + **ADR-0023** + mkdocs nav + arquitectura.md + print-formats.md.

### Ya cerrado — packs privados (working files, NO en este repo)
- Pack A (`cconsultoriaennegociosmx/erpnext_proposals_catalog`) → **2.0.0**: catálogo depurado, items
  editorial-only, pfv sin `templates`; instalador `MIN_CAPS_VERSION=12` + REQUIRED_CAPS depurado;
  `tools/normalize_program.py` ya no escribe phases/scope_items; docs actualizadas; `release.sh --create`
  (MANIFEST + releases/2.0.0 + RELEASES.md) verificado.
- Pack B (`clientesconsultoriamx/actiglobal/erpnext_proposals_catalog`) → **2.0.0**: catálogo depurado,
  items editorial-only (no tenía economic/payment/skills/designations/pfv; sin scripts propios ni manifest raíz).

### Pendiente inmediato
1. Revisión del usuario de este bloque (commit sin push).
2. Tras visto bueno: `/ship push` → `/ship pr` (base version-16; el merge lo hace el usuario).
3. E2E de una propuesta en QA con el pack v2.0.0 (Items ya en Desk) para confirmar contenido editorial + PF.

### No repetir / atención
- El loader **nunca** crea Items: en un site nuevo, los Items deben existir en Desk antes de aplicar el pack.
- `erpnext_proposals_deployment/` (sibling de Pack B) es LEGACY (jul-21 + tar.gz), fuera de alcance y NO
  respaldado en PRE-LIMPIEZA — no tocar; confirmar con usuario si algún día se retira.
- Backup inmutable PRE-LIMPIEZA en `/home/erpnext/backups/erpnext_proposals-PRECLEANUP-2026-09-22/` — no modificar.

---

## Decisiones vigentes
- El pack es puramente editorial/de presentación; los maestros funcionales viven solo en Desk (ADR-0023).
- No se borra ningún dato de BD; la depuración solo retira la distribución por archivo.
- `_seed_print_format_versions` conserva deshabilitar-anterior + changelog; el repunte de plantillas pasa a Desk.
- Versión app 0.28.0 (MINOR); si se considera "breaking" la retirada de capacidades del loader, sería 1.0.0
  — decisión del usuario antes del push (ajustable con un commit nuevo, nunca amend).

## Información faltante
- Confirmar con el usuario el nivel SemVer del bump (0.28.0 vs 1.0.0) antes del push.
