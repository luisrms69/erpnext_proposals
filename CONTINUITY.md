# Documento de Continuidad — erpnext_proposals

**Fecha:** 2026-05-23
**Para:** Nueva sesión Claude Code abriendo este app
**Desde:** PR #19 — feat(proposals): proposal versioning — new version from rejected quotation

---

## Qué es este app

`erpnext_proposals` es una app Frappe/ERPNext que agrega propuestas comerciales
profesionales sobre ERPNext Quotation — no la reemplaza.

**Concepto central:** ERPNext maneja números (precios, impuestos, costos).
Esta app agrega narrativa (secciones de propuesta, alcance técnico, versionado, PDF profesional).

---

## Estado actual del app

- **Versión:** 0.0.1 (en desarrollo)
- **Branch protegida:** `version-16` — NUNCA commitear directo ahí
- **Branch activa:** `feature/proposal-versioning` → PR #19 abierto (pendiente de merge)
- **GitHub:** https://github.com/luisrms69/erpnext_proposals
- **Site de desarrollo:** `proposals.dev` → `localhost:8405`
- **Site de tests:** `test-erpnext_proposals.localhost`
- **Remote:** `upstream` (no `origin`)

---

## Cómo ponerte al tanto

### Paso 1 — Leer los CLAUDE.md

```
1. /home/erpnext/frappe-bench-v16/.claude/CLAUDE.md          ← reglas globales del ecosistema
2. /home/erpnext/frappe-bench-v16/apps/erpnext_proposals/CLAUDE.md  ← este app
```

### Paso 2 — Leer la arquitectura

```
docs/adr/0000-estado-inicial-app.md   ← arquitectura MVP aprobada
docs/adr/0001-mvp-etapa-1-implementacion.md
docs/adr/0002-rentabilidad-estimada-propuesta.md
```

### Paso 3 — Verificar estado del PR

```bash
gh pr list --state open
gh pr view 19
```

---

## Funcionalidades implementadas

### DocTypes

| DocType | Tipo | Propósito |
|---|---|---|
| `Proposal Section` | Maestro | Sección narrativa reutilizable |
| `Proposal Template` | Maestro | Agrupa secciones en orden |
| `Proposal Template Section` | Child | Fila de sección en template |
| `Scope Item` | Maestro | Catálogo de alcances sin precio |
| `Quotation Scope Item` | Child | Copia congelada en Quotation |

### Custom Fields en Quotation (fixtures)

**Sección Propuesta:**
`proposal_template`, `proposal_title`, `quotation_scope_items`,
`proposal_cost_center`, `proposal_project`

**Sección Versionado:**
`proposal_group`, `proposal_version`, `previous_proposal`,
`superseded_by_proposal`

**Sección Revisión:**
`proposal_revision_reason`, `proposal_revision_summary`,
`proposal_reviewed_by`, `proposal_reviewed_on`,
`proposal_approved_by`, `proposal_approved_on`

**Snapshot (freeze):**
`proposal_sections_snapshot`

### Workflow

`Propuesta Comercial` — 5 estados, 7 transiciones en Quotation:
- Borrador → En Revision → Aprobada
- En Revision → Rechazada
- Aprobada → Enviada al Cliente

### Print Formats

- `Propuesta Comercial` — PDF cliente (portada navy, secciones narrativas, scope, inversión)
- `Rentabilidad Estimada` — PDF interno (costos, márgenes por designación)

### Roles

`Proposals Manager`, `Proposals User`

### Lógica backend

| Archivo | Propósito |
|---|---|
| `utils/quotation.py` | Hooks de Quotation, freeze de snapshot, generación de scope items |
| `utils/proposal_versioning.py` | Versionado controlado — `create_new_proposal_version`, guards de unicidad |
| `utils/workflow_validations.py` | Validaciones de transición de workflow |
| `utils/cost_matrix.py` | Matriz de costos por designación/actividad |
| `utils/printing.py` | Helpers Jinja para Print Formats |
| `utils/project.py` | Creación de Project desde Scope Items |
| `utils/sales_order.py` | Hook de Sales Order |

### Flujo de versionado (implementado en PR #19)

1. Propuesta llega a **Rechazada** (submitted, docstatus=1)
2. Botón **"Crear nueva versión"** solicita motivo y resumen
3. Se crea nueva Quotation con `proposal_version = N+1`, `previous_proposal = nombre_anterior`
4. La anterior queda marcada con `superseded_by_proposal` — bloqueada en workflow
5. La nueva arranca en Borrador lista para editar

**Guards activos:**
- `proposal_group` inmutable una vez asignada versión (backend + JS read_only)
- Solo una versión activa por `proposal_group` (`assert_single_live_proposal_for_group`)
- `Update Items` bloqueado en `before_update_after_submit` + oculto vía controller patch
- `Project` solo creatable desde versión vigente (no superseded)

---

## Issues abiertos relevantes

| # | Título | Prioridad |
|---|---|---|
| #18 | fix(ui): ocultar Sales Order y Set as Lost en proposals submitted | Alta — siguiente |
| #17 | feat: auto-populate proposal_group desde Frappe CRM Opportunity | Media |
| #15 | feat: selector de paleta de colores por cotización | Baja |

**#18 es el siguiente a implementar.** Usa el mismo patrón de monkey-patch ya aplicado
para `Update Items` en `public/js/quotation.js` (onload handler).

---

## Tests

```bash
bench --site test-erpnext_proposals.localhost run-tests --app erpnext_proposals
```

- **70 passed / 3 skipped** (estado al merge de PR #19)
- Tests unitarios en: `erpnext_proposals/erpnext_proposals/tests/`
  - `test_proposal_versioning.py` — suite de versionado, guards, trazabilidad
  - `test_frozen_quotation_integrity.py` — integridad del snapshot congelado
  - `test_print_format_integrity.py` — integridad del Print Format

---

## Comandos frecuentes

```bash
# Desarrollo
bench --site proposals.dev migrate
bench --site proposals.dev export-fixtures --app erpnext_proposals
bench build --app erpnext_proposals

# Tests
bench --site test-erpnext_proposals.localhost run-tests --app erpnext_proposals

# Abrir en navegador
frappe-multisite   # opción para erpnext_proposals → localhost:8405
```

---

## Reglas git del proyecto

- Remote: `upstream` (no `origin`)
- PRs siempre a `version-16`
- Nunca commitear en `version-16` directamente
- Linters antes de commit: `ruff check` + `ruff format` (.py), `prettier@2.7.1` (.js)
- Semgrep corre en CI — reglas Frappe: no usar `cur_frm`, no `frappe.throw` sin `_()`, etc.
- Fixtures: exportar con `bench export-fixtures` después de cambios de Custom Fields
