# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-05-27
**Rama activa:** `feature/issue18-hide-native-buttons`
**Tarea actual:** Issue #18 — ocultar botones nativos ERPNext en proposals + estado Ganada

---

## Recuperación rápida

Estoy trabajando en:
Issue #18: ocultar `Update Items`, `Set as Lost` y `Sales Order` en Quotations con
`proposal_group`. `Sales Order` solo se muestra en estado `Ganada` (cliente aceptó).
Se extendió el workflow agregando el estado `Ganada` con dos transiciones nuevas
desde `Enviada al Cliente`.

Plan que estoy siguiendo:
Issue #18 en GitHub — feature/issue18-hide-native-buttons

Objetivo inmediato:
Commit está listo y confirmado por el usuario. Siguiente: `/ship push` → `/ship pr`.

Criterio de avance:
PR mergeado a version-16. Issue #18 cerrado.

---

## Estado actual

### Ya cerrado
- Issue #13 — versionado de propuestas (PR #19, mergeado)
- Issue #16 — PDF polish (PR #16, mergeado)
- Issue #14 — submit quotations on review + PDF attach (PR #14, mergeado)

### En progreso
- Issue #18 — commit listo, pendiente push + PR

### Pendiente inmediato
1. `/ship push` a upstream/feature/issue18-hide-native-buttons
2. `/ship pr` a version-16 (Closes #18)
3. `/sync-check` post-merge + actualizar CONTINUITY.md

### No repetir
- No usar `cur_frm` en JS — Frappe v16 lo deprecó, semgrep en CI lo bloquea.
  Usar siempre el parámetro `frm` del event handler.
- No commitear en `version-16` directamente — siempre rama feature.
- Remote es `upstream`, no `origin`.
- CONTINUITY.md se genera con `/update-continuity` post-confirmación de commit,
  no antes de confirmar y no en commit separado.

---

## Decisiones vigentes

- **`Ganada`** es el único estado donde `Sales Order` es válida — cliente aceptó formalmente.
- **`Rechazada`** se reutiliza para rechazo de cliente (desde `Enviada al Cliente`) y
  rechazo interno (desde `En Revision`) — mismo estado, dos caminos de entrada.
- **Crear Proyecto** restringido a `Ganada` — solo cuando cliente acepta.
- `declare_enquiry_lost` bloqueado via `extend_doctype_class` mixin (backend guard) porque
  usa `db_set` y bypassa todos los hooks de Frappe.
- `custom_field.json` tiene reorden de campos del export-fixtures — es ruido cosmético, se incluye
  en el commit para mantener el round-trip limpio.

---

## Archivos relevantes ahora

### Leer primero
- `erpnext_proposals/public/js/quotation.js` — lógica de botones y monkey-patch
- `erpnext_proposals/erpnext_proposals/overrides/quotation_override.py` — backend guard
- `erpnext_proposals/fixtures/workflow.json` — workflow con Ganada + 2 transiciones nuevas

### Probablemente editar
- Ninguno hasta el próximo issue

### No tocar
- `version-16` directamente
- `test-erpnext_proposals.localhost` manualmente

---

## Funcionalidades implementadas (acumulado)

### Workflow Propuesta Comercial
6 estados: Borrador → En Revision → Aprobada → Enviada al Cliente → Ganada
                                  ↓ Rechazada (interno o por cliente)
9 transiciones totales.

### Guards de botones nativos (Issue #18)
- `Update Items`: oculto en todas las proposals submitted
- `Set as Lost`: oculto en todas las proposals submitted
- `Sales Order`: oculto excepto en Ganada
- `declare_enquiry_lost`: bloqueado en backend (mixin)

### Versionado (PR #19)
- `proposal_group` / `proposal_version` / `previous_proposal` / `superseded_by_proposal`
- Botón "Crear nueva versión" desde Rechazada
- Guard: una sola versión activa por grupo

### Print Formats
- `Propuesta Comercial` — PDF cliente
- `Rentabilidad Estimada` — PDF interno

### Proyecto desde Scope Items
- Botón "Crear Proyecto desde Propuesta" — solo en Ganada

---

## Tests

```bash
bench --site test-erpnext_proposals.localhost run-tests --app erpnext_proposals
```

- **72 passed / 3 skipped** (estado en feature/issue18-hide-native-buttons)
- `test_native_button_guards.py` — 2 tests: backend guard declare_enquiry_lost

---

## Issues abiertos

| # | Título | Prioridad |
|---|---|---|
| #17 | feat: auto-populate proposal_group desde Frappe CRM Opportunity | Media |
| #15 | feat: selector de paleta de colores por cotización | Baja |

---

## Reglas git del proyecto

- Remote: `upstream` (no `origin`)
- PRs siempre a `version-16`
- Linters: `ruff check` + `ruff format` (.py), `prettier@2.7.1` (.js)
- Semgrep en CI — no `cur_frm`, no `frappe.throw` sin `_()`, type hints en funciones
- Site dev: `proposals.dev` → `localhost:8405`
- Site tests: `test-erpnext_proposals.localhost`
