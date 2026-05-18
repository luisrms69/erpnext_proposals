# CLAUDE.md — erpnext_proposals

> **Reglas de operación Claude Code** (commits, PRs, base de datos, flujo de trabajo, prohibiciones git):
> Ver `/home/erpnext/Developer/frappe-infrastructure/.claude/CLAUDE.md`

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

*(pendiente de documentar al implementar)*

---

## Fixtures

*(pendiente — declarar en hooks.py al crear Custom Fields, Roles, Workspaces)*

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
  ruff format <archivos .py modificados>
  npx prettier@2.7.1 --write <archivos .js modificados>
  ```

### Antes de cada PR

- [ ] Linters pasados
- [ ] Fixtures exportados si hubo cambios de Custom Fields, Roles, Workspaces
- [ ] Patch creado si hay cambios de esquema — **requiere autorización explícita**
- [ ] `bench --site proposals.dev migrate` limpio
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
