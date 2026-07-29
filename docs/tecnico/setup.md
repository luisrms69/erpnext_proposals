# Entorno de desarrollo — ERPNext Proposals

---

## Requisitos

| Componente | Versión / Valor |
|---|---|
| Bench | frappe-bench-v16 (`/home/erpnext/frappe-bench-v16`) |
| Frappe | 16.x |
| ERPNext | 16.x (requerido) |
| HRMS | 16.x (requerido — fuente salarial de la matriz de costos / Rentabilidad Estimada) |
| Python | 3.12+ |
| Node | 24.x |

---

## Sites

| Site | Propósito | Puerto |
|---|---|---|
| `proposals.dev` | Desarrollo activo — migrate, export-fixtures, validación manual | 8405 |
| `test-erpnext_proposals.localhost` | Tests unitarios exclusivamente — nunca modificar manualmente | — |

**Regla:** nunca correr `bench migrate` sin `--site`. En bench compartido, afecta todos los sites.

---

## Comandos frecuentes

```bash
# Desde /home/erpnext/frappe-bench-v16

# Migrar (aplicar fixtures y patches)
bench --site proposals.dev migrate

# Exportar fixtures después de cambios en Custom Fields, Roles, Workflow
bench --site proposals.dev export-fixtures --app erpnext_proposals

# Correr tests
bench --site test-erpnext_proposals.localhost run-tests --app erpnext_proposals

# Ejecutar función Python en el site (lectura)
bench --site proposals.dev execute "<modulo.funcion>"

# Regenerar referencia técnica
python3 scripts/generate_reference.py
python3 scripts/generate_reference.py --verify  # solo verifica sin regenerar

# Build de documentación
python3 -m mkdocs build --strict
```

---

## Linters

El CI corre ruff check + ruff format. Correr en ese orden localmente antes de commit:

```bash
# Desde la raíz del app
/home/erpnext/frappe-bench-v16/env/bin/ruff check <archivos .py modificados> --fix
/home/erpnext/frappe-bench-v16/env/bin/ruff format <archivos .py modificados>

# Para JS
npx prettier@2.7.1 --write <archivos .js modificados>
```

El CI también corre semgrep con reglas Frappe. Reglas más comunes que bloquean:
- `frappe-manual-commit` → `frappe.db.commit()` sin `# nosemgrep`
- `frappe-missing-translate-function-python` → `frappe.throw("...")` sin `_()`
- `frappe-ssti` → `frappe.render_template(user_content)` sin `# nosemgrep`

---

## Tests

```bash
bench --site test-erpnext_proposals.localhost run-tests --app erpnext_proposals
```

Suites disponibles (en `erpnext_proposals/erpnext_proposals/tests/`):

| Archivo | Qué cubre |
|---|---|
| `test_proposal_versioning.py` | Guards de versionado, flujo de creación de versiones, casos límite |
| `test_project_guard_consistency.py` | Guards de creación de proyecto, contrato JS↔Python, idempotencia |
| `test_proposal_permissions.py` | Permisos por rol en los 3 endpoints whitelisted |

---

## Fixtures

Los fixtures se exportan al modificar Custom Fields, Roles, Workflows o Workflow States:

```bash
bench --site proposals.dev export-fixtures --app erpnext_proposals
```

Fixtures versionados en `erpnext_proposals/fixtures/`:

| Fixture | Contenido |
|---|---|
| `custom_field.json` | ~25 custom fields en Quotation (pestaña Propuesta) |
| `role.json` | Roles `Proposals Manager` y `Proposals User` |
| `workflow.json` | Workflow "Propuesta Comercial" — 6 estados, 7 transiciones |
| `workflow_state.json` | Estados: Borrador, En Revision, Aprobada, Rechazada, Enviada al Cliente, Ganada |

---

## Print Formats

Los Print Formats se recargan en el site después de editar el JSON:

```bash
bench --site proposals.dev execute \
  "frappe.reload_doc('ERPNext Proposals', 'Print Format', 'Propuesta Comercial', force=True)"

bench --site proposals.dev execute \
  "frappe.reload_doc('ERPNext Proposals', 'Print Format', 'Rentabilidad Estimada', force=True)"
```

Ver `docs/tecnico/print-formats.md` para el flujo completo de cambios.

---

## Restricciones operativas

- **No commitear en `version-16`** — es la rama protegida del ecosistema Frappe upstream. Todo cambio va en rama feature → PR → merge.
- **No correr tests en `proposals.dev`** — usar `test-erpnext_proposals.localhost` exclusivamente.
- **`docs/referencia/` es generado** — no editar manualmente. Regenerar con `python3 scripts/generate_reference.py`.
- **Servidor de desarrollo**: usar `frappe-multisite --docs erpnext_proposals` para el servidor MkDocs. No iniciar manualmente con `mkdocs serve` en background.

---

## Catálogo inicial

`install.py` (`after_install`) **no** siembra contenido comercial: solo sincroniza el Desktop Icon
de la app. **Ningún** Proposal Section, Template, Item, Scope Item, Phase, Print Format ni Payment
Term se crea en `install` ni en `migrate` (evita contaminar producción y cada nuevo install). Ver
[ADR-0006](../adr/0006-separacion-app-generica-personalizacion-privada.md).

Todo el contenido comercial se carga **explícitamente** con el loader genérico e idempotente, desde
un kit de catálogo externo (privado por cliente, fuera del repo):

```bash
bench --site <site> execute \
  erpnext_proposals.erpnext_proposals.catalog_data.catalog_loader.run \
  --kwargs "{'catalog_path': '/ruta/al/catalogo.json', 'update_content': True, 'dry_run': True}"
```
