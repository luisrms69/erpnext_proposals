# ADR-0001: MVP Etapa 1 — Implementación inicial

**Fecha:** 2026-05-18
**Status:** Activo
**Branch:** feature/mvp-etapa-1-doctypes

---

## Contexto

Primera implementación funcional del app `erpnext_proposals`. Objetivo: PDF de propuesta
comercial usable sobre ERPNext Quotation, sin reemplazar la lógica nativa de precios.

---

## Qué se implementó

### DocTypes creados

| DocType | Tipo | Propósito |
|---|---|---|
| `Proposal Section` | Maestro | Bloques de texto reutilizables (título + contenido HTML) |
| `Proposal Template` | Maestro | Agrupa secciones en orden con override de título/contenido |
| `Proposal Template Section` | Child | Filas de Proposal Template con sequence auto-asignado |
| `Scope Item` | Maestro | Catálogo de alcance técnico — sin precio, sin costo |
| `Quotation Scope Item` | Child | Alcance congelado dentro de Quotation al momento de selección |

### Custom Fields en Quotation (fixtures)

| Campo | Tipo | Pestaña |
|---|---|---|
| `proposal_details_section` | Tab Break "Propuesta" | — |
| `proposal_template` | Link: Proposal Template | Propuesta |
| `proposal_title` | Data | Propuesta |
| `quotation_scope_items` | Table: Quotation Scope Item | Propuesta |

### JS

- `quotation_scope_item.js`: freeze de campos al seleccionar `scope_item` en el grid
- `public/js/quotation.js` (doctype_js): filtro `enabled=1` en el grid inline

### Print Format "Propuesta Comercial" (Jinja)

Secciones renderizadas:
1. Portada — `proposal_title`, cliente, fecha, vigencia, folio
2. Secciones del template — leídas dinámicamente desde `proposal_template` (no almacenadas en Quotation)
3. Alcance propuesto — `quotation_scope_items` filtrado por `include_in_proposal`, agrupado por `phase`
4. Perfiles considerados — designations únicas de scope items
5. Inversión — `doc.items` nativo con totales de Quotation
6. Condiciones comerciales — `doc.terms` nativo

---

## Decisiones confirmadas

- **Proposal Template se renderiza dinámicamente** en el Print Format. No se almacenan las secciones en Quotation. Cambiar el template cambia el PDF retroactivamente — decisión intencional para MVP.
- **Quotation Items es la única tabla comercial.** `quotation_scope_items` es narrativa técnica, independiente de precios.
- **Scope Items se congelan** al agregarlos a Quotation. Cambios al catálogo no afectan propuestas históricas.
- **`phase` es Data libre**, no DocType. Agrupa visualmente en el PDF.

---

## Problema identificado en prueba de concepto

El campo `erpnext_item` en `Scope Item` y `Quotation Scope Item` **no tiene utilidad clara en Etapa 1**.

El flujo actual obliga a:
1. Seleccionar `scope_item` en `quotation_scope_items` (alcance técnico)
2. Agregar por separado el mismo concepto en `items` nativos (precio)

Esto crea duplicación cognitiva. El link a `erpnext_item` no resuelve el problema porque
no hay ningún mecanismo que use esa referencia para agregar automáticamente el Item a
Quotation Items.

**Pendiente de diseño para Etapa 2:**
- ¿Cómo vincular un Scope Item con su Item comercial de forma que tenga sentido en el flujo?
- Opciones a evaluar: botón "Agregar a Items", auto-agregar al seleccionar scope item, o eliminar el campo `erpnext_item` si no tendrá uso funcional.

---

## Pendiente Etapa 2

- Resolver el vínculo Scope Item → Quotation Item (diseño pendiente)
- Workspace para navegación del módulo
- Roles y permisos específicos (`Proposals Manager`, `Proposals User`)
- Ajuste de diseño del Print Format con datos reales
