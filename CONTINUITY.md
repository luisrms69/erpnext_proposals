# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-07-30
**Rama activa:** `feat/quotation-fiscal-taxes` (base `0f74e86` = `upstream/version-16`, PR #33 ya mergeado + release v0.1.0).
**Tarea actual:** **Impuesto automático en Quotation** reutilizando **por import (read-only)** la resolución fiscal de `facturacion_mexico` — adapter exclusivo en `erpnext_proposals` (`utils/quotation_tax.py`, hook `Quotation.before_validate`). `facturacion_mexico` **no se modifica**. Solo aplica con `quotation_to == "Customer"`; usa `proposal_cost_center` → CC→Branch→zona→STCT; no-op suave si falta config (no bloquea); respeta `taxes_and_charges` manual; sin validación SAT estricta de Sales Invoice. Ver **ADR-0008**. 9/9 tests nuevos OK; suite completa **235 OK / 1 skip**; ruff + `mkdocs --strict` limpios.

---

## Recuperación rápida

Estoy trabajando en:
Commit del adapter fiscal de Quotation en `feat/quotation-fiscal-taxes` vía `/ship commit`. Alcance:
`utils/quotation_tax.py` (nuevo), hook `Quotation.before_validate` en `hooks.py`,
`tests/test_quotation_fiscal_taxes.py` (9 tests) + documentación pública (ADR-0008, arquitectura,
flujo-operativo, CHANGELOG, mkdocs nav). `facturacion_mexico` sin cambios (solo import de sus helpers).

Plan que estoy siguiendo:
1. `/ship commit` del adapter + docs (hecho en este bloque).
2. **Bump `__version__` → 0.2.0** (feat → MINOR) ANTES del PR — no incluido en este commit por alcance;
   el gate SemVer de `/ship pr` lo exige.
3. `/ship push` → PR hacia `version-16` cuando se autorice.
4. Pendientes en paralelo (fuera del repo público): versionamiento formal del kit privado
   (`sha256sum -c` + marker de versión instalada + git privado); falso warning de logo del instalador
   (rutas DFP `/file/...`); proceso CRM Deal→Customer para contacto/linkage. Ver el análisis de secuencia.

Criterio de avance:
Cada paso con autorización explícita; nunca escritura en BD/servidores sin aviso. Git solo vía `/ship`.
[[feedback_git_solo_via_ship]]

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

### Commits posteriores en la rama (docs, versión y CI)
- Documentación del gate (arquitectura, print-formats, **ADR-0007** contenido editorial en Item, referencia
  regenerada, `mkdocs.yml`); `mkdocs build --strict` limpio.
- `chore(release): 0.1.0` — bump SemVer (MINOR) por el alcance del PR.
- `ci: instalar facturacion_mexico en el workflow` (`bench get-app --branch main` + `install-app`).
- `test(proposals): Item Group hoja determinista` — helper `get_test_item_group()` en `tests/company.py`
  usado por los 12 tests que crean `Item`; resuelve `MandatoryError: item_group` en el site fresco de CI.
- `test(proposals): Cost Center y Price List deterministas` — helpers `get_test_cost_center()` /
  `get_test_price_list()`; `test_sections_snapshot` y `test_print_format_resolution` los usan y setean
  `selling_price_list`. Resuelve `MandatoryError` (selling_price_list / proposal_cost_center) al
  re-guardar/versionar Quotations en el site fresco. Validado en `ci-mirror-proposals.localhost`.

- `test(proposals): sembrar Party Type y Warehouse Type` — helper `_ensure_shared_masters()` en
  `tests/company.py` (llamado por `get_test_company`): siembra `Warehouse Type "Transit"` y
  `Party Type Customer/Supplier` con `account_type`. Sin ellos, crear la Company falla
  (`create_default_warehouses` → LinkValidationError "Goods In Transit") y el validate de la Quotation
  revienta en `get_party_account` (`AttributeError NoneType.lower`). Con Transit pre-sembrado la Company
  se crea con su árbol de cuentas completo (`default_receivable_account`).

### Site espejo de CI (reproducción local) — CLAVE
`ci-mirror-proposals.localhost` = `bench new-site` + install `erpnext`/`hrms`/`facturacion_mexico`/
`erpnext_proposals` **sin Setup Wizard**, idéntico al pipeline de CI (misma erpnext 16.27). Reproduce los
fallos de CI localmente (~10s/corrida) en vez de ~13 min por ciclo. **Para validar el camino de creación
fresca de la Company** hay que borrar `_Test Proposals Co` y re-correr (si no, se reusa la Company vieja
y no se ejercita el path). Suite ahí (fresh company): **143 OK / 11 skip / 0 errores**.

### Verificación
- Suite completa `erpnext_proposals`: **226 OK (1 skip)** con `facturacion_mexico` instalada.
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
