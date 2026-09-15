# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-14
**Rama activa:** `feat/addenda-change-control-v2` (base `upstream/version-16` = v0.23.0)
**Tarea actual:** Change Control v2 — **B1, B2, B3 y fingerprint cerrados**; cerrando con **PR contra `version-16`** (bump **0.24.0**). Integración con `pmo` NO iniciada.

---

## Recuperación rápida

Estoy trabajando en:
Change Control v2 de `erpnext_proposals`. Bloque 0 documental cerrado (ADR-0019 §7). B1 (gate venta neta),
B2 (apply-split), B3 (required_items al versionar) y el fingerprint canónico del delta de addenda.

Plan que estoy siguiendo:
Contratos entregados por el usuario + ADR-0019 §7 / §7.1 / §7.2 / §7.4 y ADR-0020 (porción económica).

Objetivo inmediato:
Fingerprint validado → commit + push en `feat/addenda-change-control-v2`. **No** PR/tag/Release. **No** guard
de re-aprobación en `pmo`.

Criterio de avance:
Commit real revisable antes de autorizar el bloque siguiente (integración/guard en `pmo`).

---

## Estado actual

### Ya cerrado
- **B1** (`workflow_validations.py`): gate `net_total>0` solo root. Commit `3b58830`.
- **B2** (`utils/project.py`, apply-split): `apply_addendum_to_project` Fase 1 (asocia+sync) / Fase 2
  (materializa solo si hay scope ejecutable). Commit `fb49cd1`.
- **B3** (`utils/proposal_versioning.py`): `_copy_required_item` copia solo semántica al versionar. Commit `dee5e54`.
- **Fingerprint** (`utils/addendum.py`, ADR-0019 §7.2): `get_addendum_delta_fingerprint(quotation) -> str`
  (read-only, server-side, NO whitelisted). SHA-256 de un payload canónico (revenue/labor/external) del delta
  SEMÁNTICO CONGELADO. Fail-closed: addenda canónica + `docstatus>=1` + `assert_economic_snapshot_complete`.
  Commit inicial `75a6e56`; **corrección de revisión (pendiente de commit):**
  - `labor` ahora incluye los campos de MATERIALIZACIÓN: `item_code`, `phase`, `include_in_proposal`,
    `is_internal_cost_task` (deciden ejecutabilidad y Task-fase; sin ellos dos versiones con distinta
    ejecutabilidad/fase producían la misma huella). Se EXCLUYEN `title`/`description`/`deliverable` (narrativos).
  - `_canon_dependency_codes`: **fail-closed** (valor presente no interpretable como lista → lanza, no `[]`),
    semántica de **conjunto** (dedupe: `["A","A"]==["A"]`).
  - **Causa raíz del `except` sin paréntesis:** `ruff format` (0.15.12 local) **elimina** los paréntesis del
    tuple `except (ValueError, TypeError):` → forma sin paréntesis. Fix definitivo: `# fmt: skip` en esa línea
    para que ruff (local y CI v0.14.10) preserve `except (ValueError, TypeError):`. Verificado: ruff format no
    la altera, ruff check pasa, `py_compile` + import real OK. Commit `78c79bf` (parcial) + corrección publicada.
  - Incluye porción económica de líneas vendidas (`proposal_economic_behavior`/interval/count) vía ADR-0020.
  - `tests/test_addendum_fingerprint.py` (32): +flags/phase/item_code sensibles, deps fail-closed/dedupe/vacío.

### Pendiente inmediato
1. Integración con `pmo` (registro de la huella aprobada + guard de `apply` fail-closed). **NO iniciar sin
   autorización.** Fuera de este bloque: `pmo`, guards de re-aprobación, estados/workflow, schema.

### No repetir
- La huella NO incluye `name`/versión/`previous_proposal`/`proposal_project`/timestamps/IDs técnicos.
- NO convertir colecciones a `set` (rompería multiplicidad). NO depender del orden físico de child rows.
- NO usar el fingerprint todavía para aplicar/bloquear addendas. `pmo` lo consumirá, no lo calcula.
- `test_09b` (#60) falla solo local (`allow_multiple_items=1`); pasa en CI.

---

## Decisiones vigentes
- Porción económica del fingerprint (comportamiento de líneas vendidas) = interpretación de §7.2 que remite a
  ADR-0020; NO es ampliación del contrato. Si faltara un campo material para el delta económico, DETENERSE
  y reportar antes de ampliar (no fue necesario).
- Canonicalización: `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` + SHA-256; filas
  ordenadas por su representación canónica preservando duplicados; `dependency_scope_item_codes` por conjunto.

---

## Archivos relevantes ahora
### Leer primero
- `erpnext_proposals/erpnext_proposals/utils/addendum.py` (`get_addendum_delta_fingerprint` + helpers)
- `docs/adr/0019-aplicar-addendum-a-project-existente.md` (§7.2) · `docs/adr/0020-*.md` (porción económica)
### No tocar
- `apply_addendum_to_project`, B1/B2/B3, freeze, `pmo`, permisos/estados/workflow/schema.

---

## Riesgos / cuidados
- `test_09b` (#60) es la única falla de suite y es ambiental local (no del cambio).

## Información faltante
- Definición concreta de la integración con `pmo` (se recibirá tras revisar el commit del fingerprint).
