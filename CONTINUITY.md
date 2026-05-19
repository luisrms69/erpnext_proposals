# Documento de Continuidad — erpnext_proposals

**Fecha:** 2026-05-18
**Para:** Nueva sesión Claude Code abriendo este app en VS Code
**Desde:** Sesión anterior (llantascs_customs + diseño arquitectónico)

---

## Qué es este app

`erpnext_proposals` es una app Frappe/ERPNext nueva, recién scaffoldeada.
Agrega propuestas comerciales profesionales sobre ERPNext Quotation — no la reemplaza.

**Concepto central:** ERPNext maneja números (precios, impuestos, costos).
Esta app agrega narrativa (secciones de propuesta, alcance técnico, PDF profesional).

---

## Estado actual del app

- **Versión:** 0.0.1 — solo scaffold, sin DocTypes implementados todavía
- **Branch:** `version-16` (estándar Frappe upstream — NO `main` ni `develop`)
- **GitHub:** https://github.com/luisrms69/erpnext_proposals
- **Site de desarrollo:** `proposals.dev` → `localhost:8405`
- **Site de tests:** `test-erpnext_proposals.localhost`
- **Apps instaladas en ambos sites:** frappe + erpnext + erpnext_proposals

---

## Cómo ponerte al tanto

### Paso 1 — Leer los 3 niveles de CLAUDE.md

```
1. /home/erpnext/Developer/frappe-infrastructure/.claude/CLAUDE.md  ← reglas globales del ecosistema
2. /home/erpnext/frappe-bench-v16/.claude/CLAUDE.md                 ← contexto del bench v16
3. /home/erpnext/frappe-bench-v16/apps/erpnext_proposals/CLAUDE.md  ← este app
```

Los 3 son obligatorios antes de tocar nada.

### Paso 2 — Leer la arquitectura aprobada

La arquitectura del app fue diseñada y aprobada en la sesión anterior.
Está documentada en:

```
docs/adr/0000-estado-inicial-app.md
```

El resumen:
- 4 DocTypes nuevos: `Proposal Section`, `Proposal Template`, `Scope Item`, `Quotation Scope Item` (child)
- Custom Fields en Quotation: `proposal_template`, `proposal_title`, tabla `quotation_scope_items`
- Print Format Jinja para PDF profesional (8 secciones)
- Sin lógica de precios ni costos en el app — todo viene de ERPNext nativo

### Paso 3 — Entender el ecosistema de comandos

Tienes disponibles los slash commands de frappe-infrastructure vía symlink:
```
.claude/commands/ → /home/erpnext/Developer/frappe-infrastructure/.claude/commands/
```

Comandos clave:
- `/ship commit` / `/ship push` / `/ship pr` — flujo de git seguro
- `/safe-point` — backup antes de cambios delicados
- `/new-doctype` — crear DocTypes con la guía del ecosistema
- `/audit-frappe-app` — auditoría estática del código
- `/test-guard` — correr tests de forma segura

### Paso 4 — Entender las reglas git

- Rama protegida: `version-16` — NUNCA commitear directo ahí
- Todo cambio: crear feature branch desde `version-16`, PR → `version-16`
- Remote se llama `upstream` (no `origin`)
- `/ship pr` apunta a `version-16`

---

## Arquitectura MVP — Etapa 1 (lo que hay que implementar)

### DocTypes a crear (en orden recomendado)

1. **`Proposal Section`** — bloques de texto reutilizables
   - Campos: `section_name`, `section_type` (Select), `title`, `content` (Text Editor), `enabled`

2. **`Proposal Template`** — agrupa secciones en orden
   - Campos: `template_name`, `description`
   - Child table: `Proposal Template Section` (sequence, proposal_section Link, custom_title, include_by_default)

3. **`Scope Item`** — alcance técnico vendible (sin precios)
   - Campos: `code`, `title`, `description` (Text Editor), `deliverable` (Text Editor)
   - `phase` (Data — solo narrativo), `erpnext_item` (Link:Item)
   - `default_activity_type` (Link:Activity Type), `default_designation` (Link:Designation)
   - `estimated_hours` (Float), `visible_in_proposal` (Check), `enabled` (Check)
   - Nota: `phase`, `activity_type`, `designation` son preparatorios para Etapa 3 — no funcionales en MVP

4. **`Quotation Scope Item`** — child table para Quotation (datos congelados)
   - Campos: `scope_item` (Link), `code`, `title`, `description`, `deliverable`, `phase`
   - `erpnext_item` (Link:Item), `activity_type` (Link), `designation` (Link)
   - `estimated_hours` (Float), `include_in_proposal` (Check)

5. **Custom Fields en Quotation** (via fixtures, no DocType):
   - `proposal_template` (Link:Proposal Template)
   - `proposal_title` (Data)
   - `quotation_scope_items` (Table:Quotation Scope Item)

6. **JS en Quotation** (`doctype_js`):
   - Al seleccionar `proposal_template` → cargar secciones marcadas `include_by_default`
   - Al agregar fila en `quotation_scope_items` → congelar campos del Scope Item

7. **Print Format "Propuesta Comercial"** (Jinja HTML):
   Estructura aprobada del PDF:
   ```
   1. Portada (logo, cliente, título, fecha, vigencia, autor)
   2. Objetivo y modalidad
   3. Alcance propuesto (tabla Scope Items por Phase)
   4. Perfiles considerados (Designations de Scope Items)
   5. Entregables
   6. Supuestos y exclusiones (Proposal Sections)
   7. Inversión (Quotation Items nativos)
   8. Condiciones comerciales (Terms and Conditions)
   ```

### Lo que NO entra en Etapa 1

- Botón "Agregar Scope Items a Items" (Etapa 2)
- Conversión a Project/Tasks (Etapa 3)
- Aprobación interna de propuesta

---

## Decisiones arquitectónicas importantes (no negociar sin consultar)

1. **Scope Item no tiene precios ni costos** — todo precio viene de ERPNext Item/Item Price
2. **Quotation Items es la única tabla comercial** — no crear tabla paralela de precios
3. **Al agregar Scope Item a Quotation, los datos se CONGELAN** — cambiar el catálogo no afecta propuestas históricas
4. **`phase` es Data simple** — no crear DocType para fases en MVP
5. **`designation` y `activity_type` en Scope Item son preparatorios** — no tienen uso funcional en Etapa 1
6. **Las dos tablas son independientes**: puede haber Scope Items sin Quotation Items y viceversa

---

## Comandos de trabajo frecuentes

```bash
# Desarrollo
bench --site proposals.dev migrate
bench --site proposals.dev export-fixtures --app erpnext_proposals
bench build --app erpnext_proposals

# Tests
bench --site test-erpnext_proposals.localhost run-tests --app erpnext_proposals

# Abrir en navegador (correr en terminal externo)
frappe-multisite   # seleccionar opción 4 (erpnext_proposals → localhost:8405)
```

---

## Contexto del ecosistema Buzola

- **Infraestructura:** `frappe-infrastructure` en `/home/erpnext/Developer/frappe-infrastructure/`
- **Comandos globales:** `.claude/commands/` (symlink desde cada app)
- **Checkpoints/backups:** `frappe-infrastructure/checkpoints/`
- **Multisite script:** `/home/erpnext/bin/frappe-multisite`
- **GitHub owner:** `luisrms69`
- **Email Buzola:** `it@buzola.mx`

### Otras apps del ecosistema (referencia)

| App | Branch | Bench | Site dev |
|---|---|---|---|
| `llantascs_customs` | `develop` | frappe-bench-v16 | llantascs-v16.dev |
| `facturacion_mexico` | `main` | frappe-bench-v16 | facturacion-v16.dev |
| `erpnext_proposals` | `version-16` | frappe-bench-v16 | proposals.dev:8405 |

Nota: el ecosistema tiene inconsistencia histórica en nombres de rama protegida.
Los apps nuevos usan `version-16` (estándar Frappe upstream).

---

## Próximo paso

Implementar los DocTypes del MVP Etapa 1, en el orden listado arriba.
Usar `/new-doctype` para cada uno.

Antes del primer `bench migrate` real → correr `/safe-point site=proposals.dev app=erpnext_proposals`.
