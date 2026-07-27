# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-07-27
**Rama activa:** `chore/gitignore-local-artifacts` (base `a11584d` = `upstream/version-16`).
**Tarea actual:** Serie de commits de endurecimiento pre-despliegue lista para PR hacia `version-16`. Todos los cambios son genéricos y aptos para el repo público; el contenido comercial/branding sigue fuera del repo.

---

## Recuperación rápida

Estoy trabajando en:
Split en commits lógicos de la preparación pre-despliegue de `erpnext_proposals`. Toda la serie va en
**una sola rama** (`chore/gitignore-local-artifacts`), un commit por bloque funcional, para abrir **un**
PR hacia `version-16`. Suite completa **180 tests OK (1 skip)** con `facturacion_mexico` instalada en el
site de pruebas.

Plan que estoy siguiendo:
1. Serie de commits C1–C7 en la rama (hecho — ver "Commits de esta rama").
2. `/ship pr` hacia `version-16` cuando se autorice (bump de versión + gates documentales del skill).
3. Despliegue: instalar app en producción; aplicar el catálogo privado por ruta externa (`bench execute`
   del loader); smoke test.
4. Revisar una copia de la base de producción antes de aplicar el catálogo (checklist privado).

Criterio de avance:
Cada paso con autorización explícita; nunca escritura en BD/servidores sin aviso. Git solo vía `/ship`.
[[feedback_git_solo_via_ship]] · Una sola rama para toda la serie. [[feedback_una_sola_rama_commits]]

---

## Estado actual

### Ya cerrado (mergeado en `version-16`, PR #31)
- Scope interno de costo (`is_internal_cost_task`) + Project Tasks jerárquicas por fase.
- Loader genérico de catálogos por ruta externa (ADR-0006).
- Resolución + congelamiento del Print Format comercial (ADR-0005).
- Documentación (arquitectura, print-formats, ADR-0005/0006) + CI verde.

### Commits de esta rama (todos genéricos, aptos para el repo público)
1. `chore(git): ignore local one-offs and backup files` — ignora `one_offs/`, `.claude/`, `*.backup-*.json`.
2. `feat(install): stop seeding demo proposal content` — `after_install` deja de sembrar contenido demo
   (se retiraron `_create_base_catalog`/`_create_sections`/`_create_templates`; conserva `_sync_desktop_icons`).
   +4 tests que confirman una instalación nueva sin demo.
3. `feat(loader): extend catalog seeding and validation` — capacidades genéricas del `catalog_loader`:
   Items, Print Formats (+protección de formatos protegidos), Payment Terms/Templates, `null` explícito en
   Scope Items, `capabilities()`/`LOADER_CAPS_VERSION`, límite de allowlist (no toca DocTypes ajenos, no borra).
4. `test(proposals): use deterministic company in test fixtures` — helper `tests/company.py`
   (`get_test_company`) determinista en MXN; corrige la selección "primera Company" no determinista en 9
   módulos de test (evita fallos MXN/USD cuando coexisten Companies de prueba de ERPNext).
5. `chore(deps): require facturacion_mexico` — `required_apps = ["erpnext", "hrms", "facturacion_mexico"]`
   (aporta los masters fiscales que los Items referencian).
6. `feat(print): expose logo data URI for print formats` — `get_logo_data_uri` genérica: embebe un logo
   del site como `data:` URI base64 (robusto para el PDF); retorna `""` si el path está vacío o no existe.
7. `feat(print): sync quotation format from proposal template` — `sync_proposal_print_format_from_template`
   puebla `Quotation.proposal_print_format` desde `Proposal Template.print_format` durante `validate`;
   respeta la selección manual y no afecta Quotations sin plantilla; no toca el formato protegido.
8. `fix(versioning): regenerate valid payment schedule for revisions` — al crear una nueva versión NO copia
   `due_date` inválidos: conserva el Payment Terms Template si existe, deja el schedule vacío para que
   ERPNext lo regenere, y bloquea con mensaje claro los calendarios manuales no reproducibles. +tests 17/18/19.

### Verificación
- Suite completa `erpnext_proposals`: **180 OK (1 skip)** con `facturacion_mexico` instalada.
- `ruff check` / `ruff format --check` / `git diff --check` limpios. Diff público sin datos de cliente,
  folios, contenido editorial, rutas privadas ni nombres de formatos/templates privados.

### Catálogo privado (fuera del repo)
El contenido comercial (2 Proposal Templates comerciales, 12 Proposal Sections, 4 Items, 9 Proposal Phases,
29 Scope Items, 1 Print Format privado) vive en el **kit privado por ruta externa** y se aplica con el
loader genérico. Documentos del kit: `PRODUCTION_CATALOG_ALLOWLIST.md`, `PRODUCTION_CLEANUP_CHECKLIST.md`.
El loader no crea UOM ni Item Groups (masters fiscales de `facturacion_mexico`) y no borra nada.

---

## Pendientes funcionales — DIAGNOSTICADOS, NO IMPLEMENTADOS

Diseño discutido y diagnóstico entregado; **nada de esto está implementado en código todavía**:

1. **Impuestos automáticos en Quotation** — hoy no se cargan; `facturacion_mexico` solo procesa Sales
   Invoice. Vía recomendada: configuración fiscal nativa (STCT default / Tax Rule) o una API pública
   reutilizable de `facturacion_mexico`. No implementado.
2. **Centro de costos obligatorio + reglas fiscales** — hacer `proposal_cost_center` obligatorio solo con
   `proposal_template` (server + filtro por company). No implementado.
3. **Reorganización de Proposal Sections** — dejar las Sections solo para contenido universal. No implementado.
4. **Scope Items tipificados (`block_type`)** — mover el contenido específico del servicio a Scope Item /
   Quotation Scope Item con un tipo de bloque. No implementado.
5. **Inmutabilidad de Sections en el PDF** — el Print Format lee hoy la Section del maestro vivo; debe leer
   del snapshot congelado. No implementado.
6. **Revisión posterior de la base de producción** — inventario read-only + comparación contra la allowlist
   + dry-run del catálogo antes de cualquier limpieza; nada se elimina sin autorización. Pendiente de la copia.

### Nota de entorno (site de pruebas)
`facturacion_mexico` quedó **instalada en `test-erpnext_proposals.localhost`** para validar la suite con la
nueva dependencia. Correr la suite de `facturacion_mexico` en ese site dispara el bootstrap de datos de
ERPNext (crea Companies de prueba) — por eso el fix determinista de Company del commit 4.

### No repetir
- No versionar contenido de cliente (branding, catálogos reales, assets, one_offs, PDFs).
- No `git` manual — solo vía `/ship`. [[feedback_git_solo_via_ship]]
- No crear ramas adicionales — toda la serie va en la misma rama. [[feedback_una_sola_rama_commits]]
- **NUNCA** merge — lo hace el usuario. [[feedback_nunca_merge]]

---

## Decisiones vigentes
- App genérica en el repo; catálogos/branding/assets reales fuera del repo, aplicados por site (ADR-0006).
- Print Format comercial: resolución override → template → default; congelamiento del efectivo (ADR-0005).
- `facturacion_mexico` es `required_app` (aporta masters fiscales SAT); el loader solo los referencia.

---

## Riesgos / cuidados
- Despliegue toca BD y servidores → autorización explícita en cada paso; servidores dev solo vía `frappe-multisite`.
- Los pendientes funcionales (impuestos, centro de costos, sections/scope, inmutabilidad) siguen abiertos:
  no asumir que están resueltos.

## Información faltante
- Rutas/credenciales de staging y producción y ventana de despliegue (las define el usuario al iniciar).
