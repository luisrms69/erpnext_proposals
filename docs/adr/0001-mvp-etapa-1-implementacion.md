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

## RC 1.0 — rama feature/commercial-pdf-improvements (PR #8)

**Status:** En revisión — CI corriendo

### Prioridad 1 — PDF Comercial ✅
- Portada profesional: logo empresa, preparado para/por, fecha, vigencia, moneda
- Plan de Trabajo tipo deploy: fases, tareas, perfil, tipo, horas, días, totales por fase
- `sequence` editable en Quotation Scope Item para reordenar por propuesta
- Sección Inversión con net_total / impuestos / grand_total + condiciones de pago
- Bloque de aceptación: Elaboró / Revisó / Aprobó
- Known issue: HTML en Proposal Sections puede renderizar como texto literal

### Prioridad 2 — Rentabilidad Imprimible ✅
- Print Format "Rentabilidad Estimada" como segundo Print Format en Quotation
- Reutiliza `get_profitability_data()` — misma fuente que Script Report
- Secciones: Costo Laboral, Items Comprados, Resumen, Q/C Checks, Advertencias, Firmas
- Fix: "Último precio de compra" (no "Tasa de cambio de última compra")
- Items cubiertos por horas excluidos de sección Items Comprados

### Prioridad 3 — Workflow de Aprobación ✅
- Roles: `Proposals User` (crea/envía a revisión) + `Proposals Manager` (aprueba/rechaza)
- 5 estados: Borrador → En Revision → Aprobada → Rechazada → Enviada al Cliente
- Validaciones bloqueantes: sin proposal_template, cost_center o net_total=0
- Warnings: tareas sin activity_type/costing_rate, moneda distinta
- Permisos en DocTypes custom para ambos roles
- Registro via Workflow Action nativo de Frappe (sin custom fields de aprobación)

### Prioridad 4 — Post mortem
Diferida. Requiere datos reales de Timesheets contra Tasks del Project.
Arquitectura documentada en ADR-0002.

### Prioridad 5 — Catálogo Base y Workspace ✅
- 10 Proposal Sections con contenido instructivo (no texto comercial — guía para IA/usuario)
- 3 Proposal Templates: Implementación ERPNext, Integración API, Bolsa de Horas/Soporte
- Creados via `after_install` — **no se sobreescriben en migrate**
- Workspace "ERPNext Proposals" con 4 secciones: Operación, Configuración, Reportes, Referencia
- Desktop Icon y Workspace Sidebar en module folder (`{app_package}/desktop_icon/`)
- Comando requerido post-instalación: `bench --site {site} sync-desktop-icons`

**Decisiones RC 1.0:**
- Proposal Sections/Templates: `after_install` idempotente, NO fixtures (evita sobreescritura)
- Workspace Sidebar: se sincroniza en `bench migrate`
- Desktop Icon: requiere `bench sync-desktop-icons` (paso manual documentado)
- Workflow: `standard=0` no requerido — archivos en module folder evitan orphan removal
- Pre-commit CI usa `ruff-pre-commit v0.14.10` — puede formatear diferente al ruff local; aplicar diff exacto del CI si falla

## Actualización de producción — Congelación operativa de cotización y generación de PDFs (2026-05-21)

### Problema crítico identificado
El Print Format leía Proposal Sections dinámicamente en cada render. Editar una sección en el catálogo modificaba retroactivamente todas las propuestas históricas. Inaceptable para documento comercial formal.

### Decisión arquitectónica
**Punto de congelación único: `Borrador → En Revisión`.**

Una vez enviada a revisión, la versión del documento queda congelada permanentemente. No existe `unfreeze` automático.

**Estados y comportamiento:**
- `Borrador`: editable, catálogo vivo
- `En Revisión` / `Aprobada` / `Rechazada` / `Enviada al Cliente` / `Submitted`: snapshot congelado

**Campo agregado:** `proposal_sections_snapshot` (Long Text JSON, hidden) en Quotation.
Formato: `[{"sequence": 100, "title": "...", "content": "raw Jinja sin renderizar", "source_section": "...", "captured_on": "..."}]`

**Costing rates:** también se congelan en `Borrador → En Revisión` (antes era solo `before_submit`).

**Correcciones post-rechazo:** la transición `Rechazada → Borrador` está BLOQUEADA con error explícito. El usuario debe duplicar o amendar la Cotización para crear una nueva versión. Ver Issue #13 para el diseño de versionado futuro.

**Print Format:** usa snapshot si existe; catálogo vivo como fallback para documentos históricos. Warning visible si propuesta en estado congelado no tiene snapshot.

## Pendiente post-RC 1.0

- Post mortem estimado vs real (Timesheets / Sales Invoice) — pendiente
- Tests formales flujo Quotation → Project → SO — ✅ realizados manualmente en proposals.dev
- Margen mínimo configurable para bloquear aprobación — **descartado**, no se implementará
- Botones GUI para regenerar/descargar PDFs adjuntos — ✅ implementados (Imprimir Propuesta Comercial, Imprimir Rentabilidad Estimada)
- Renderizado HTML en secciones narrativas — ✅ resuelto mediante render_section_content() con detección WYSIWYG/Markdown
- Versionado de propuestas: mecanismo explícito para nueva versión post-rechazo (Issue #13) — pendiente

## Trabajo pendiente actual

| Prioridad | Ítem |
|---|---|
| 1 | **Versionado de propuestas** — nueva versión post-rechazo con trazabilidad (Issue #13) |
| 2 | **Embellecimiento del PDF** — diseño visual, portada ejecutiva, tablas, tipografía |
| 3 | **Post-mortem** — comparar costos estimados vs costos reales de ejecución (Timesheets/Invoices) |
