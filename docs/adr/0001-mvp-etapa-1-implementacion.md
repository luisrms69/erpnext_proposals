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

## Problema crítico identificado en prueba de concepto

### El doble llenado de ítems rompe la cadena de verdad

Durante la primera prueba funcional se detectó un problema arquitectónico que invalida el diseño de Etapa 1:

**El problema:**
El usuario debía llenar dos tablas distintas para el mismo concepto:

1. `quotation_scope_items` — alcance técnico (captura manual)
2. `doc.items` — línea comercial con precio (captura manual)

Estas tablas representan el mismo objeto desde dos ángulos. No son independientes: el usuario tenía que mantenerlas en sincronía manualmente. Eso no es solo UX malo — rompe la trazabilidad preventa → comercial → ejecución → finanzas.

**El objetivo real del sistema:**
El Item ERPNext es la unidad comercial analizable. Sobre él se quiere poder medir: cuántas veces se vendió, rentabilidad, margen, conversión a Sales Order/Invoice, ejecución en Project/Tasks. Si el alcance técnico no queda ligado al Item vendido, se pierde esa trazabilidad.

**Por qué `erpnext_item` era referencia pasiva:**
El campo existía en `Scope Item` y `Quotation Scope Item` pero no tenía ningún mecanismo que lo usara. Era decorativo. El problema no era el campo — era que la dirección del flujo estaba al revés.

---

## Decisión arquitectónica para Etapa 2 — APROBADA

**Modelo: Item 1 → N Scope Items**

```
Item (unidad analizable en ERPNext)
  └── Scope Items [Scope Item.erpnext_item = Item]  ← relación estructural del catálogo
         ↓ botón "Generar alcance desde Items"
Quotation Item [precio, cantidad, impuestos — solo aquí]
  └── Quotation Scope Item [item_code congelado, textos congelados]
         ↓ futuro Etapa 3
Project Task → Sales Invoice → análisis financiero por Item
```

**Cambio de rol de `Quotation Scope Item`:**
Deja de ser tabla de captura manual. Pasa a ser tabla generada y congelada desde los Items cotizados. El usuario no llena esta tabla directamente — el botón la genera a partir de `doc.items`.

**Razón para no crear `Item Scope Mapping` (N:M):**
Si un Scope Item aplica a múltiples Items sin variación técnica, probablemente es contenido del Proposal Template (sección narrativa transversal), no un Scope Item ligado a un ítem vendible. Si varía por ítem, debe ser un Scope Item distinto. N:M se añade solo si en producción aparece un patrón claro de duplicación de catálogo que no sea resuelto por esta regla.

### Cambios de Etapa 1 → Etapa 2

| Campo / DocType | Acción |
|---|---|
| `Scope Item.erpnext_item` | Mantener — cambia de referencia pasiva a relación estructural |
| `Quotation Scope Item.item_code` | Agregar — Data, congelado, referencia al Quotation Item origen |
| `Quotation Scope Item.erpnext_item` | Eliminar — reemplazado por `item_code` |
| Botón "Generar alcance desde Items" | Crear — lee `doc.items`, busca Scope Items por `erpnext_item`, congela en `quotation_scope_items` |
| Print Format | Agrupar alcance por `item_code` y/o `phase` |
| `Item Scope Mapping` | No crear — sobreingeniería prematura |

### Regla de idempotencia del botón

El botón "Generar alcance desde Items" debe ser idempotente: si se ejecuta dos veces sobre la misma Quotation, no debe duplicar filas en `quotation_scope_items`. Debe detectar combinaciones `item_code + scope_item` ya existentes y omitirlas.

---

## Pendiente Etapa 2

- Implementar los cambios de esquema aprobados arriba
- Botón "Generar alcance desde Items" con lógica idempotente
- Print Format: agrupación por `item_code` y `phase`
- Workspace para navegación del módulo
- Roles y permisos específicos (`Proposals Manager`, `Proposals User`)
- Ajuste de diseño del Print Format con datos reales
- Tests formales en `test-erpnext_proposals.localhost`
