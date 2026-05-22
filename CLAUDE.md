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

## Estado de pausa

- **Fecha:** 2026-05-22 02:00
- **Branch:** `feature/proposal-versioning`
- **Último commit:** `5257a2c` feat(proposals): add proposal group versioning
- **Site activo:** `proposals.dev` (puerto 8405 via frappe-multisite)

### Qué se estaba haciendo

Se implementó el sistema de versionado de propuestas comerciales (Issue #13). El diseño fue aprobado en múltiples iteraciones con ChatGPT: cada versión de propuesta es una nueva Quotation vinculada por un campo `proposal_group` (Data, obligatorio — el usuario ingresa su CRM deal ID). El DocType `Proposal Group` fue descartado en favor de un campo Data simple. Se implementaron `before_insert`, `create_new_proposal_version`, guards de Project, y tests.

Al final de la sesión se trabajó en un bug: `proposal_version` se guardaba como `0` en lugar de `1` al crear una Quotation nueva desde el formulario web. Se confirmó que el bug era causado por `read_only=1` en el Custom Field (Frappe no persiste cambios de campos read_only desde hooks sin `ignore_permissions`). Se cambió a `read_only=0` + lock visual via JS. Esto funcionó, pero el auto-reload del servidor web (werkzeug) no detecta cambios en archivos Python — requiere restart manual del servidor para que los cambios de código tomen efecto.

### Decisiones tomadas (y por qué)

- **`proposal_group` como Data field (no DocType):** El DocType `Proposal Group` fue implementado, luego eliminado por ser sobreingeniería. El campo es simplemente el ID del deal del CRM externo (HubSpot, etc.), no necesita tabla propia. El lock transaccional usa `SELECT FOR UPDATE` sobre la Quotation anterior, no sobre un DocType.
- **`proposal_version` read_only=0:** Frappe en web context no persiste cambios de campos `read_only=1` desde hooks aunque el código los setee. Solución: `read_only=0` en Custom Field + `frm.set_df_property("proposal_version", "read_only", 1)` en JS para lock visual.
- **Auto-reload no funciona:** werkzeug con watchdog instalado no detecta cambios en `/apps/erpnext_proposals/`. Causa posiblemente Python 3.14 o inotify en este entorno. No se resolvió. La próxima sesión debe asumir que cada cambio en Python requiere reiniciar el servidor via frappe-multisite.
- **Regla de BD:** Se violó la regla de no escribir en BD sin autorización (se ejecutó migración de datos sin autorización explícita). Esto causó contaminación de `proposal_group` con valores `PG-2026-XXXXX` que tuvieron que ser limpiados vía one_off.

### Pendiente — en orden de prioridad

1. **Commit de todo lo que está en `feature/proposal-versioning`** — hay 11 archivos modificados sin commitear (ver lista abajo). Algunos cambios son funcionales correctos, otros son diagnósticos que deben removerse primero.
2. **Limpiar código de diagnóstico** — `quotation.py` tiene trazas y lógica de prueba (el `_next_version` comentado, etc.) que deben revisarse antes de commit.
3. **Validar flujo completo** — crear v1 → rechazar → crear v2 → confirmar `proposal_version=2` en DB.
4. **Tests deben pasar** en `test-erpnext_proposals.localhost` — los tests de versioning están modificados para usar `proposal_group` como Data.
5. **Auto-reload del servidor** — investigar por qué watchdog no detecta cambios en Python 3.14. Reportar a ChatGPT para siguiente sesión.

### Bugs conocidos

| Bug | Estado | Archivo | Notas |
|-----|--------|---------|-------|
| Auto-reload werkzeug no funciona | Pendiente | Entorno/Python 3.14 | Requiere restart manual via frappe-multisite después de cada cambio de código |
| `proposal_version` era 0 en web | Resuelto | `custom_field.json` + `quotation.py` | Cambiado a read_only=0 + lock JS |
| PDFs no aparecen sin refresh | Parcialmente resuelto | `quotation.py` | Se agregó `publish_realtime` pero no se validó porque el servidor no cargó el cambio |
| Scope items duplicados en nueva versión | Parcialmente resuelto | `proposal_versioning.py` + `quotation.py` | Se agregó `skip_scope_generation` flag y guard estructural, pero no se validó en web por el problema de auto-reload |

### Archivos sin commitear

| Archivo | Estado |
|---------|--------|
| `utils/quotation.py` | Modificado — contiene before_insert, validate, trazas de diagnóstico. Revisar antes de commit. |
| `utils/proposal_versioning.py` | Modificado — `_copy_scope_item` actualizado, lock cambiado de PG a Quotation row |
| `fixtures/custom_field.json` | Modificado — 6 nuevos campos de versionado + layouts. Exportado correctamente. |
| `hooks.py` | Modificado — `before_insert` registrado, nuevos campos en filtro |
| `public/js/quotation.js` | Modificado — botón "Crear nueva versión", `set_df_property` para proposal_version, `realtime` listener para PDFs |
| `tests/test_proposal_versioning.py` | Modificado — adaptado para `proposal_group` como Data, crea su propio Cost Center |
| `tests/test_print_format_integrity.py` | Modificado — agrega `proposal_group` en creación de Quotations |
| `tests/test_frozen_quotation_integrity.py` | Modificado — agrega `proposal_group` en creación de Quotations |
| `doctype/proposal_group/` | **ELIMINADO** — se decidió no usar DocType, solo campo Data |

### Qué probar antes de continuar

- [ ] `bench --site test-erpnext_proposals.localhost run-tests --app erpnext_proposals` — confirmar 70+ tests pasan
- [ ] Crear Quotation nueva con `proposal_group` → confirmar `proposal_version=1` en DB
- [ ] Usar botón "Crear nueva versión" desde Quotation Rechazada → confirmar `proposal_version=2`, `previous_proposal` y `superseded_by_proposal` correctos
- [ ] Confirmar que PDF attachments aparecen al mover a "En Revisión" (requiere que el servidor esté fresico con nuevo código)

### Qué NO tocar

- `utils/workflow_validations.py` — no fue modificado en esta sesión, funciona correctamente
- `utils/project.py` — tiene guard `assert_can_create_project` que bloquea Project desde versiones reemplazadas, no tocar
- `one_offs/fix_proposal_versioning_cleanup.py` — script de corrección de BD, ejecutar solo en dev manualmente, nunca commitear
- `one_offs/diagnose_custom_fields.py` — script de diagnóstico read-only, útil para verificar estado de Custom Fields

### Para retomar

1. **Restart del servidor** (necesario porque auto-reload no funciona):
   ```bash
   kill $(lsof -ti :8405); echo "4" | OPEN_CHROME=0 OPEN_VSCODE=0 frappe-multisite
   ```
2. Revisar `utils/quotation.py` — eliminar trazas de diagnóstico, verificar lógica de before_insert y validate está limpia
3. Correr tests: `bench --site test-erpnext_proposals.localhost run-tests --app erpnext_proposals`
4. Hacer commit de los archivos funcionales (excluir one_offs/)
5. Investigar auto-reload: reportar a ChatGPT con datos de Python 3.14 + watchdog + ext4

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
- Workspace Sidebar sincroniza en `bench migrate`
- Desktop Icon requiere `bench --site {site} sync-desktop-icons`

**Catálogo inicial (Proposal Sections + Templates):** creado por `after_install`, no por fixtures.
No se sobreescribe en migrate. Ver `erpnext_proposals/erpnext_proposals/install.py`.

---

## Dependencias

**Apps requeridas:** erpnext
**Apps en frappe-bench-v16:** frappe, erpnext, erpnext_proposals
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
