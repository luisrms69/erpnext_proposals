# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-06-29
**Rama activa:** `feature/proposal-phase-catalog`
**Tarea actual:** Catálogo `Proposal Phase` (base de fases) + endurecer pruebas de inmutabilidad y su aislamiento.

---

## Recuperación rápida

Estoy trabajando en:
La primera pieza del rediseño de fases: un catálogo `Proposal Phase` (DocType maestro),
con cobertura de pruebas de inmutabilidad de la propuesta y aislamiento del entorno de
pruebas. La fase aún NO se conectó al alcance.

Plan que estoy siguiendo:
Diseño acordado con el usuario (en la conversación): Proposal Phase → (futuro) Proposal
Scope Template → Item → copia congelada en Quotation → Tasks padre por fase. Por ahora
SOLO el catálogo.

Objetivo inmediato:
Commit de `feature/proposal-phase-catalog`, luego push y PR a `version-16`.

Criterio de avance:
Suite completa verde y aislada (122 OK, 3 skips, 0 fail, 0 err); catálogo migrado e
inmutable; sin conexión todavía al flujo.

---

## Estado actual

### Ya cerrado
- DocType `Proposal Phase`: `phase_code` (estable, inmutable: autoname + `set_only_once` +
  guard en `validate` + `before_rename`), `phase_name` (title_field), `sequence`, `enabled`.
  Permisos espejo de Scope Item.
- Pruebas de inmutabilidad del catálogo (13) y de la propuesta completa (16).
- Helper común `tests/fiscal_year.py`; los módulos que crean Quotations aseguran/limpian su
  propio Fiscal Year (aislamiento). Sin `before_tests`.
- Docs: `docs/usuario/doctypes.md`, referencia regenerada, `CLAUDE.md`.

### En progreso
- **PR #26 abierto** (https://github.com/luisrms69/erpnext_proposals/pull/26) hacia `version-16` — esperando checks/review/merge.

### Pendiente inmediato
1. Merge del PR #26 (tras checks de CI). Antes de "Squash and Merge": re-`/update-continuity` final.
2. Siguiente etapa de diseño (NO implementada): `Proposal Scope Template` + Item→Template +
   copia congelada de fase (Link de referencia + snapshot `phase`/`phase_sequence`) + Tasks
   padre por fase. Presentar diseño completo de inmutabilidad antes de implementar.

### No repetir
- **NUNCA** conectar `Proposal Phase` al alcance sin diseñar antes la copia congelada
  (snapshot inmutable), no un Link vivo: un rename del catálogo alteraría propuestas históricas.
- `set_only_once` por sí solo NO basta para inmutabilidad cuando el campo es el autoname →
  usar guard explícito en `validate`.
- Una prueba no debe crear datos persistentes que otras necesiten (FY): usar el helper
  `tests/fiscal_year.py` (crea solo si falta, elimina solo si lo creó).
- **NUNCA** `reload_doc(..., 'workspace', ..., force=True)` con `developer_mode` (borra el archivo).
- Remote es `upstream` (no `origin`). No commitear en `version-16`. `docs/referencia/` es generada.

---

## Decisiones vigentes
- La fase es propiedad del USO (Quotation Scope Item / Scope Template), no del maestro Scope Item.
- En la propuesta la fase debe ser **Link de referencia + snapshot congelado** (`phase`, `phase_sequence`); el consumo (PDF/reporte/proyecto) usa el snapshot, no el catálogo vivo.
- La propuesta es inmutable tras submit (`docstatus=1` + `allow_on_submit=0` + `freeze_proposal`); cambios → nueva versión.
- `Proposal Phase` autoname `field:phase_code` para que el name sea estable.

---

## Archivos relevantes ahora

### Leer primero
- `doctype/proposal_phase/` — el catálogo.
- `tests/test_proposal_immutability.py` — qué inmutabilidad está garantizada.
- `tests/fiscal_year.py` — helper de aislamiento.

### Probablemente editar (etapa futura, no ahora)
- `utils/quotation.py` (auto-copy), `doctype/quotation_scope_item/` (snapshot de fase), un nuevo `Proposal Scope Template`.

### No tocar
- No conectar `Proposal Phase` al flujo todavía.

---

## Riesgos / cuidados
- `migrate` escribe en BD — siempre con `--site`.
- En CI, los tests que crean Quotations hacen SkipTest si no hay Company; localmente requieren Fiscal Year (resuelto por el helper).

---

## Información faltante
- Diseño final del `Proposal Scope Template` y de la herencia Item→alcance.
- Generador de PDF (`pdf_generator`) de los Print Formats — pendiente de etapas previas.
