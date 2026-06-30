# CLAUDE.md — erpnext_proposals

> **Reglas de operación Claude Code** (commits, PRs, base de datos, flujo de trabajo, prohibiciones git):
> Ver `/home/erpnext/Developer/frappe-infrastructure/.claude/CLAUDE.md`

---

## ⛔ PROHIBICIONES ABSOLUTAS — PRIMER NIVEL

Estas reglas anulan cualquier otra instrucción. No hay excepción ni autorización posible.

1. **NUNCA escribir en la base de datos** — ni `frappe.db.set_value`, ni `frappe.db.sql`, ni `frappe.get_doc().save()` ejecutado desde `bench execute`. Cero escrituras a BD desde Claude.

2. **NUNCA crear patches** — ni proponer, ni generar, ni sugerir patches como solución. Los patches son responsabilidad exclusiva del desarrollador.

3. **Flujo obligatorio para Custom Fields:**
   - Editar el fixture JSON (`fixtures/custom_field.json`) directamente con los valores correctos
   - Correr `bench --site proposals.dev migrate` — Frappe aplica el fixture a la BD vía su propia API
   - Correr `bench --site proposals.dev export-fixtures --app erpnext_proposals` — verifica round-trip
   - Commit

4. **Checkpoint obligatorio después de cada bloque funcional** antes de continuar al siguiente:
   ```bash
   bench --site proposals.dev migrate
   bench --site proposals.dev export-fixtures --app erpnext_proposals
   git add -A
   git commit -m "checkpoint: <descripción>"
   ```

---

## Print Format — Control de cambios

El Print Format `Propuesta Comercial` (`print_format/propuesta_comercial/propuesta_comercial.json`) es el único archivo que controla el PDF de propuesta. Su fuente de verdad es Git.

**Regla de producción:** nunca editar el Print Format directamente en ERPNext UI como cambio permanente. Si se prueba en UI → replicar en el JSON → commit → PR.

**Flujo obligatorio para cambios al Print Format:**
1. Rama `feature/print-*`
2. Editar solo `propuesta_comercial.json` (CSS/HTML/Jinja)
3. `bench --site proposals.dev execute "frappe.reload_doc('ERPNext Proposals', 'Print Format', 'Propuesta Comercial', force=True)"`
4. Generar PDF y revisar visualmente
5. Commit con prefijo `style(print):` o `feat(print):` o `refactor(print):`
6. Agregar PDF de evidencia a `docs/visual-regression/propuesta-comercial/`
7. PR con PDF adjunto en la descripción
8. Merge
9. En producción: `bench --site <site> execute "frappe.reload_doc(..., force=True)"`

**Carpeta de evidencia visual:** `docs/visual-regression/propuesta-comercial/`
Ver `docs/visual-regression/propuesta-comercial/README.md` para convención de nombres.

---

## Estado del proyecto

- **App nueva:** creada en frappe-bench-v16
- **Bench activo:** `/home/erpnext/frappe-bench-v16`
- **Branch protegida:** `version-16` (nunca commitear directamente — estándar Frappe)
- **Versión:** 0.0.1 (desarrollo inicial)
- **En producción:** No

---

## Sites de desarrollo y prueba

| Site | Bench | Propósito | Notas |
|---|---|---|---|
| `proposals.dev` | frappe-bench-v16 | Desarrollo activo | Features, migrate, export-fixtures |
| `test-erpnext_proposals.localhost` | frappe-bench-v16 | Tests unitarios | Solo para `bench run-tests` — nunca modificar manualmente |

**Reglas de uso:**
- `bench migrate` → siempre con `--site`. Nunca sin site en bench compartido.
- `bench run-tests` → siempre `test-erpnext_proposals.localhost` — nunca en el site de desarrollo.
- `bench export-fixtures` → `proposals.dev`

**Apps en test-erpnext_proposals.localhost:** frappe, erpnext, erpnext_proposals

## Entorno
Ver contexto global en `frappe-infrastructure/.claude/CLAUDE.md`.

**Comandos frecuentes (bench v16):**
```bash
bench --site proposals.dev migrate
bench --site proposals.dev export-fixtures --app erpnext_proposals
bench --site proposals.dev run-tests --app erpnext_proposals
bench build --app erpnext_proposals
```
**NUNCA:** `bench migrate` sin `--site` — afecta todos los sites del bench compartido

---

## Qué hace esta app

App de propuestas comerciales profesionales sobre ERPNext Quotation. Agrega una capa
de estructura narrativa (Proposal Templates, Proposal Sections, Scope Items) encima
del flujo nativo de cotización, permitiendo generar PDFs de propuesta profesionales
sin reemplazar Quotation Items ni crear sistemas paralelos de precios.

---

## DocTypes principales

| DocType | Tipo | Propósito |
|---|---|---|
| `Proposal Section` | Maestro | Sección narrativa reutilizable (bloque de texto del cuerpo de la propuesta) |
| `Proposal Template` | Maestro | Agrupa secciones en orden — define estructura del PDF por tipo de proyecto |
| `Proposal Template Section` | Child | Fila de sección en un template (con override opcional de título y contenido) |
| `Scope Item` | Maestro | Catálogo de actividades/alcances — sin precio, sin costo |
| `Quotation Scope Item` | Child | Copia congelada del catálogo dentro de una Quotation específica |
| `Proposal Phase` | Maestro | Catálogo único de fases (`phase_code` estable e inmutable + `phase_name`/`sequence`/`enabled` editables). Aún NO conectado al alcance |

**Custom Fields en Quotation (pestaña "Propuesta"):**
`proposal_template`, `proposal_title`, `quotation_scope_items`, `proposal_cost_center`, `proposal_project`

**Print Formats:** `Propuesta Comercial` (cliente), `Rentabilidad Estimada` (interno)
**Script Report:** `Profitability Estimate` — fuente de cálculo compartida con el Print Format interno

**Documentación de usuario:** `docs/usuario/`

---

## Fixtures

| Fixture | Archivo | Contenido |
|---|---|---|
| Custom Field | `fixtures/custom_field.json` | 6 campos en Quotation (pestaña Propuesta) |
| Role | `fixtures/role.json` | `Proposals Manager`, `Proposals User` |
| Workflow | `fixtures/workflow.json` | "Propuesta Comercial" — 5 estados, 7 transiciones en Quotation |
| Workflow State | `fixtures/workflow_state.json` | Borrador, En Revision, Aprobada, Rechazada, Enviada al Cliente |

**Workspace, Workspace Sidebar, Desktop Icon:** module folder (no fixtures).
- Workspace Sidebar sincroniza en `bench migrate` — su primer item `Inicio` (link_type `Workspace`) aterriza en el Workspace de tarjetas, no en el primer DocType
- Desktop Icon se sincroniza automáticamente en `after_install` (ver `_sync_desktop_icons` en `install.py`). En sites ya instalados, aplicar con `bench --site {site} sync-desktop-icons`

**Catálogo inicial (Proposal Sections + Templates):** creado por `after_install`, no por fixtures.
No se sobreescribe en migrate. Ver `erpnext_proposals/erpnext_proposals/install.py`.

---

## Dependencias

**Apps requeridas:** erpnext, hrms (ambas en `required_apps` — hrms es fuente salarial de la matriz de costos / Rentabilidad Estimada)
**Apps en frappe-bench-v16:** frappe, erpnext, hrms, erpnext_proposals
**Dependencias externas:** Ninguna

---

## Tests

```bash
bench --site test-erpnext_proposals.localhost run-tests --app erpnext_proposals
```

**Sin cobertura inicial.** Documentar tests aquí cuando se implementen.
**Site de tests dedicado:** `test-erpnext_proposals.localhost` — nunca correr tests en el site de desarrollo.

---

## REGLAS GIT — ERPNEXT_PROPOSALS

### Antes de cada commit

- Correr linters en archivos modificados:
  ```bash
  ruff check <archivos .py>      # detecta errores e imports
  ruff format <archivos .py>     # aplica formato
  npx prettier@2.7.1 --write <archivos .js>
  ```

### Antes de cada PR

- [ ] Linters pasados (ruff check + ruff format + prettier)
  **Nota:** CI usa `ruff-pre-commit v0.14.10` que puede formatear diferente al ruff local.
  Si CI falla con `ruff-format`, aplicar el diff exacto del CI y recomitear.
- [ ] Semgrep pasado — el CI corre `semgrep` con reglas de Frappe:
  ```bash
  git clone --depth 1 https://github.com/frappe/semgrep-rules.git /tmp/frappe-semgrep-rules
  semgrep --config /tmp/frappe-semgrep-rules/rules --config r/python.lang.correctness <archivos .py>
  ```
  Reglas comunes que bloquean CI:
  - `frappe-manual-commit` → `frappe.db.commit()` sin justificación (usar `# nosemgrep` si es necesario en tests)
  - `frappe-missing-translate-function-python` → `frappe.throw("...")` sin `_()`
  - `security.missing-argument-type-hint` → funciones sin type hints
- [ ] Fixtures exportados si hubo cambios de Custom Fields, Roles, Workspaces
- [ ] Patch creado si hay cambios de esquema — **requiere autorización explícita**
- [ ] `bench --site proposals.dev migrate` limpio
- [ ] `/doc-review` ejecutado — si hubo cambios en DocTypes, JS, utils, workflow o print formats:
  - Declarar estado por área:
    - `✅ Docs actualizadas` — se actualizó `docs/usuario/` en este PR
    - `⚪ No aplica` — cambio interno sin impacto visible
    - `⚠️ Pendiente / riesgo aceptado` — riesgo documentado
  - `mkdocs build --strict` debe pasar antes de abrir el PR
- [ ] Ver checklist global en `frappe-infrastructure/CONTRIBUTING.md`

### PROHIBICIÓN ABSOLUTA — NUNCA TRABAJAR EN version-16

**`version-16` es la rama protegida de erpnext_proposals. Es el estándar Frappe upstream.**

Nota: otros repos Buzola usan `main` (facturacion_mexico) o `develop` (llantascs_customs)
por razones históricas. Los apps nuevos del ecosistema usan `version-16` alineado con
frappe/erpnext/hrms upstream.

- **Nunca implementar cambios estando en `version-16`.**
- **Nunca crear commits estando en `version-16`.**
- Todo cambio debe iniciar en una rama feature creada desde `version-16` limpio.
- `/ship commit` y `/ship commit-push` deben rechazar si la rama es `version-16`.
- `/ship pr` debe exigir rama distinta de `version-16`.

### Reglas específicas del proyecto

- PRs siempre a `version-16`
- Site de desarrollo: `proposals.dev` → `localhost:8405`
- Site de tests: `test-erpnext_proposals.localhost`
