# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-08-13
**Rama activa:** `fix/pf-version-disabled-owner-and-historical-guard` (base `upstream/version-16` = **v0.9.0**).
**Tarea actual:** **App 0.9.1** — endurecer el ciclo de versionamiento de Print Formats del loader (fix de idempotencia estructural + guard histórico en dry-run). Complementa el fix declarativo ya desplegado del pack 1.24.0.

---

## Recuperación rápida

Estoy trabajando en:
`/ship commit` de **v0.9.1** en `fix/pf-version-disabled-owner-and-historical-guard`. Dos cambios en `catalog_data/catalog_loader.py`:
- **A.2:** `_seed_print_formats(..., superseded=set)` — para un Print Format listado en `supersedes` (de `print_format_versions`), el seeder **no gestiona `disabled`**; el versionador (`_seed_print_format_versions`) es su único dueño → elimina el flip-flop que rompía la idempotencia (residual `disabled` en el `--apply` de 1.23.0).
- **B:** si el plan cambiaría html/css/presentación de un Print Format **histórico** (`is_print_format_historical`), el loader lo reporta como **`conflict`** desde `--dry-run`, antes de que ADR-0011 lo bloquee en el `--apply`. `disabled` queda fuera del guard.

Próximo paso concreto:
Tras autorización: `/ship push` → `/ship pr` (base `version-16`). Tras merge del usuario: `/sync-check` + tag/Release **v0.9.1** (`/ship release`). **No** mezclar con un nuevo despliegue del pack a prod.

Criterio de avance:
Cada paso con autorización explícita separada; git solo vía `/ship` [[feedback_git_solo_via_ship]]; nunca merge (lo hace el usuario) [[feedback_nunca_merge]]. Sin escritura en BD/servidores sin aviso.

---

## Estado actual

### Ya cerrado
- **App v0.9.0** (PR #45, squash `ecec974`) — versionamiento de Print Formats: selector central, ADR-0011 (retiró `disabled` del guard), loader v8 `print_format_versions`. Tag+Release publicados.
- **Pack privado 1.24.0** — sellado (`releases/1.24.0/`) y transferido a prod (`~/private-kits/releases/1.24.0/`). Fix declarativo A.1 (formato anterior con `disabled: 1` en `print_formats`) + reporte detallado en instalador + `RUNBOOK-despliegue.md`. Corrige el residual de idempotencia del 1.23.0.

### En progreso (esta rama, 0.9.1)
- A.2 + B implementados en `catalog_loader.py`; `superseded_pf` cableado en `run()`.
- Tests nuevos: `test_a2_versioner_owns_disabled_of_superseded`, `test_b_historical_content_change_is_conflict`.
- Doc: `docs/tecnico/print-formats.md` — sección "Aplicación por el loader del pack".
- Bump `0.9.0 → 0.9.1` (PATCH). `caps_version` sigue **8** (cambios internos, no capacidad nueva).
- Validado: suite **327 OK / 1 skip**; ruff check+format limpios; `mkdocs --strict` limpio.

### Pendiente inmediato
1. `/ship commit` (autorizado) → reportar hash + working tree limpio.
2. `/ship push`.
3. `/ship pr` a `version-16`. **No** hacer merge ni release hasta reportar el PR.

### Verificación de prod (tarea del usuario, cierre separado — no bloquea este commit)
- En `erp.buzola.mx` correr solo `--check` + `--dry-run` de 1.24.0. Esperado **0/0/0**. **No** `--apply`, ni backup, ni `bench migrate`. Si el dry-run muestra algo ≠ 0/0/0 → detenerse y reportar.

### No repetir
- No versionar contenido de cliente (branding, catálogos reales, assets, PDFs, one_offs). Gate de datos de cliente.
- No `git` manual — solo vía `/ship` [[feedback_git_solo_via_ship]]. **NUNCA** merge — lo hace el usuario [[feedback_nunca_merge]].
- No re-desplegar el pack a prod como parte de 0.9.1.
- En prod: `git`/`bench` como usuario **`erpnext`** (no `luisrms69` → dubious ownership).

---

## Decisiones vigentes
- **Dueño único de `disabled`:** en el ciclo de versionamiento, solo `_seed_print_format_versions` cambia `disabled` del formato sustituido. `_seed_print_formats` lo excluye vía el set `superseded`. Declarar el anterior con `disabled: 1` en `print_formats` es además lo consistente (evita el flip-flop aun sin A.2).
- **Guard histórico en el loader (B):** cambiar presentación de un Print Format histórico es `conflict` en dry-run; `disabled` no es presentación (permitido por el modelo, ADR-0011 "Actualización 2026-08-12").
- **ADR-0011:** históricos (`proposal_effective_print_format`) protegidos en html/css/rename/delete; el registro oficial son los PDFs adjuntos del freeze, no la reimpresión.
- App genérica en el repo; catálogos/branding/assets reales en packs privados por ruta externa (ADR-0006). Cada cliente tiene su propio sitio y pack [[reference_clientes_packs_sites]].

---

## Archivos relevantes ahora

### Leer primero
- `erpnext_proposals/erpnext_proposals/catalog_data/catalog_loader.py` — `_seed_print_formats` (A.2/B), `run()` (`superseded_pf`), `_seed_print_format_versions`.
- `erpnext_proposals/erpnext_proposals/utils/print_format_protection.py` — `is_print_format_historical`, `_PRESENTATION_FIELDS`.

### Probablemente editar
- Solo si CI pide ajustes de lint/formato.

### No tocar
- `releases/*` del pack privado (inmutables). `docs/adr/0011-*.md` (ya cerrado).

---

## Riesgos / cuidados
- 0.9.1 no requiere `bench migrate` (sin esquema/fixtures) ni `bench build` (sin JS). Solo código Python del loader.
- El comportamiento nuevo del loader solo se observa al aplicar packs; los tests lo cubren con datos ficticios.
