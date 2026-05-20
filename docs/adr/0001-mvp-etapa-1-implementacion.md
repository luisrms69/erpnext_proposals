# ADR-0001: MVP Etapa 1 — Implementación inicial

**Fecha:** 2026-05-18
**Status:** Cerrado — MVP validado con tests
**Branch:** feature/mvp-etapa-1-doctypes → mergeado a version-16
**Validado:** 2026-05-19 — prueba funcional con datos de producción en proposals.dev
**Tests:** 21/21 pasando en test-erpnext_proposals.localhost (2026-05-19)
**Validación 1:N:** Item → Scope Items exitosa con datos reales

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

## Estado de implementación Etapa 2

**Implementado y mergeado a version-16:**
- `Quotation Scope Item`: campos `item_code` (frozen) y `auto_generated` agregados
- `erpnext_item` deprecado (hidden, no eliminado)
- `doc_events` hook: auto-genera alcance en `validate` si `proposal_template` está definido
- Idempotente por `item_code + scope_item` — verificado con test
- Botón secundario "Regenerar alcance" en grupo Propuesta

**Validaciones completadas:**
- Relación 1:N Item → Scope Items validada con datos reales de producción (erp.buzola.mx)
- Print Format renderiza correctamente con datos reales
- 21/21 tests pasando en test-erpnext_proposals.localhost

## Cobertura de tests

| Test | Descripción | Estado |
|---|---|---|
| `test_create` (Proposal Section) | Crear sección, verificar nombre | ✅ |
| `test_title_defaults_to_section_name` | Title default cuando vacío | ✅ |
| `test_mandatory_section_name` | ValidationError sin nombre | ✅ |
| `test_create` (Proposal Template) | Crear template sin secciones | ✅ |
| `test_auto_sequence` | Sequence 10/20/30 auto-asignado | ✅ |
| `test_sequence_respects_existing` | Sequence respeta valores previos | ✅ |
| `test_custom_title_and_content` | Override título y contenido en sección | ✅ |
| `test_mandatory_template_name` | ValidationError sin nombre | ✅ |
| `test_create` (Scope Item) | Crear scope item básico | ✅ |
| `test_create_with_erpnext_item` | Scope item con Item ERPNext vinculado | ✅ |
| `test_mandatory_code` / `test_mandatory_title` | Campos obligatorios | ✅ |
| `test_no_price_fields` (Scope Item) | Sin campos comerciales | ✅ |
| `test_no_price_fields` (QSI) | Sin campos comerciales en child | ✅ |
| `test_is_child_table` | istable = 1 | ✅ |
| `test_required_fields_exist` | Campos esperados presentes | ✅ |
| `test_scope_items_generated_on_save` | Auto-generación con proposal_template | ✅ |
| `test_generation_is_idempotent` | No duplica en segundo save | ✅ |
| `test_quotation_items_unchanged` | Items comerciales intactos | ✅ |
| `test_no_scope_without_proposal_template` | Caso negativo | ✅ |
| `test_print_format_renders` | PDF no lanza excepción | ✅ |

## Etapa 3 — Deploy Plan (rama feature/deploy-sequence-pdf)

**Decisión arquitectónica aprobada:**
```
Quotation (ganada) → Project + Tasks → Sales Order → vinculación automática
```

**Implementado:**
- `sequence` en `Scope Item` y `Quotation Scope Item` (editable por propuesta)
- Print Format "Plan de Trabajo": tabla con fase/tarea/perfil/tipo/horas/días, totales por fase y proyecto
- Descripción de cada tarea visible bajo el título en el PDF
- `proposal_project` (Link:Project, allow_on_submit) en Quotation — se llena al crear el proyecto
- `proposal_cost_center` (Link:Cost Center, **obligatorio**) en Quotation
- Botón "Crear Proyecto desde Propuesta" en Quotation submitted
- `utils/project.py`: crea Project+Tasks desde Quotation, propaga customer y cost_center, idempotente
- `utils/sales_order.py`: auto-llena `SO.project` y `SO.cost_center` en validate; vincula `Project.sales_order` en submit
- ERPNext 16: `prevdoc_docname` en lugar de `prevdoc_doctype` (removido en v16)

**Validaciones en proposals.dev (2026-05-19):**
- Botón "Crear Proyecto desde Propuesta" funciona en Quotation submitted ✅
- Project creado con customer y cost_center desde Quotation ✅
- Tasks generadas desde Quotation Scope Items con horas correctas ✅
- `SO.project` auto-llenado al validar Sales Order creada desde Quotation ✅
- `SO.cost_center` propagado desde `proposal_cost_center` ✅
- `Project.sales_order` vinculado al submitir SO ✅
- PDF "Plan de Trabajo" muestra fases en orden correcto, descripción por tarea, totales ✅
- 5 Quotations de prueba con horas reales creadas en proposals.dev ✅
- `proposal_cost_center` marcado como campo obligatorio ✅

**Decisiones confirmadas en esta etapa:**
- No usar estado "Won" en Quotation — botón visible en cualquier Quotation submitted
- `sequence` editable en Quotation Scope Item (no solo en catálogo)
- Project es la fuente de verdad del deploy — nace en Quotation, no en SO
- ERPNext Activity Type como fuente de costo/hora para etapa futura de rentabilidad

## Etapa 4 — Rentabilidad Estimada (ADR-0002, mergeado PR #7)

Script Report `Profitability Estimate` implementado y mergeado a version-16:
- Costo laboral: Quotation Scope Items × Activity Type.costing_rate
- Costo items: jerarquía Supplier Quotation → Buying Item Price → Last Purchase Rate → Valuation Rate
- Anti-duplicación por item_code en items_with_scope
- Margen sobre net_total (antes de impuestos)
- Advertencias por falta de activity_type, costing_rate, costo de item, y discrepancia de moneda
- Validado con SAL-QTN-2026-00008: venta $212,500 | costo $104,200 | margen 51%

## Roadmap priorizado (aprobado 2026-05-20)

| Prioridad | Área | Objetivo |
|---|---|---|
| 1 | **PDF comercial** | Propuesta visualmente profesional y vendible |
| 2 | **Rentabilidad imprimible** | Reporte interno presentable para revisión/autorización |
| 3 | **Aprobación interna** | Workflow para validar propuesta antes de enviar al cliente |
| 4 | **Post mortem** | Comparar estimado vs real (horas, costo, margen) |
| 5 | **Catálogo/demo** | Templates, Scope Items y datos ejemplo listos para demo |

## Pendiente Etapas siguientes

- PDF comercial: portada, espaciado, tablas, plan de trabajo legible, inversión clara
- Reporte de rentabilidad con formato imprimible
- Workflow de aprobación interna (advertencias de costeo incompleto, margen mínimo)
- Post mortem estimado vs real via Timesheets y Sales Invoice
- Catálogo demo: 2-3 templates, 10-20 Scope Items reales, Activity Types con tarifas
- Workspace para navegación del módulo
- Roles y permisos específicos (`Proposals Manager`, `Proposals User`)
- Tests formales para flujo Quotation → Project → SO
