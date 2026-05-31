# Arquitectura técnica — ERPNext Proposals

> Estado actual implementado. No incluye historia ni planes futuros.
> Última actualización: 2026-05-30

---

## Resumen

App Frappe sobre ERPNext que extiende `Quotation` con un flujo de aprobación interna,
generación de PDFs de propuesta comercial, catálogo de alcances y creación de proyectos
de ejecución. No reemplaza el flujo nativo de cotización — lo amplía con una capa narrativa
y de gestión.

---

## Módulos principales

| Módulo | Responsabilidad | Archivos clave | Estado |
|---|---|---|---|
| Workflow de aprobación | Validaciones y trazabilidad en transiciones de estado | `utils/workflow_validations.py` | Activo |
| Lifecycle de Quotation | Hooks de inserción, validación, submit y post-submit | `utils/quotation.py` | Activo |
| Versionado de propuestas | Crear nueva versión desde propuesta Rechazada | `utils/proposal_versioning.py` | Activo |
| Creación de proyecto | Crear Proyecto + Tasks desde Quotation Ganada | `utils/project.py` | Activo |
| Matriz de costos | Rebuild periódico de costos por Designation + Activity Type | `utils/cost_matrix.py` | Activo |
| Permisos | Guard de roles para endpoints críticos | `utils/permissions.py` | Activo |
| Print Formats | PDF Propuesta Comercial (público) y Rentabilidad Estimada (privado) | `print_format/`, `utils/printing.py` | Activo |
| Reporte de rentabilidad | Fuente de datos compartida entre UI y Print Format | `report/profitability_estimate/` | Activo |
| Override de Quotation | Bloquea `declare_enquiry_lost` en propuestas con workflow | `overrides/quotation_override.py` | Activo |
| Sales Order hooks | Propaga proyecto y cost center de Quotation a SO | `utils/sales_order.py` | Activo |

---

## Flujos principales

| Flujo | Entrada | Proceso | Salida | Docs relacionados |
|---|---|---|---|---|
| Creación de propuesta | Nueva Quotation con `proposal_group` | `before_insert` valida grupo único; `validate` genera scope items desde catálogo | Quotation en Borrador con scope | `utils/quotation.py` |
| Avance a En Revision | Workflow action "Enviar a Revision" | `validate_workflow`: valida campos, congela snapshot de secciones y costos, genera y adjunta PDFs | Quotation submitted (docstatus=1), snapshot congelado, PDFs adjuntos | `utils/workflow_validations.py` |
| Aprobación / Rechazo | Workflow action "Aprobar" o "Rechazar" | Registra `reviewed_by`, `reviewed_on`; si aprobada: registra `approved_by`, `approved_on` | Quotation en Aprobada o Rechazada con trazabilidad | `utils/workflow_validations.py` |
| Versionado | Quotation Rechazada + acción "Crear nueva versión" | Copia campos a nueva Quotation; marca original como `superseded_by_proposal`; bloquea si hay proyecto activo en la versión anterior | Nueva Quotation en Borrador vinculada | `utils/proposal_versioning.py` |
| Marcar como Ganada | Workflow action "Marcar como Ganada" | Transición Enviada al Cliente → Ganada | Quotation en estado Ganada; habilita botón Crear Proyecto y Sales Order | `fixtures/workflow.json` |
| Crear proyecto | Botón "Crear/Ver Proyecto" (estado Ganada) | Crea Project + Tasks desde scope items; idempotente: reutiliza proyecto si ya existe | Proyecto ERPNext con Tasks vinculadas a scope items | `utils/project.py` |
| Propagación a Sales Order | Creación de SO desde Quotation Ganada | `validate` y `on_submit` propagan `proposal_project` y `proposal_cost_center` al SO | SO con proyecto y cost center heredados | `utils/sales_order.py` |
| Rebuild de costos | Scheduler diario o acción manual | Lee Activity Cost, Timesheets, Salary Assignments; upsert en Proposal Cost Matrix | Matriz actualizada; Log de cambios de tasa | `utils/cost_matrix.py` |

---

## DocTypes críticos

| DocType | Propósito | Relaciones | Notas |
|---|---|---|---|
| `Proposal Section` | Bloque de texto narrativo reutilizable | Referenciado por `Proposal Template Section` | Tiene flag `is_executive_summary` para resaltar en portada |
| `Proposal Template` | Agrupa secciones en orden para un tipo de proyecto | Tiene child table `Proposal Template Section` | 3 templates instalados por `install.py` |
| `Proposal Template Section` | Fila de sección en un template | Link a `Proposal Section`; soporte para `custom_title` y `custom_content` | Child table de `Proposal Template` |
| `Scope Item` | Actividad del catálogo maestro | Link a `Item` de ERPNext (`erpnext_item`) | Sin precio; describe trabajo, perfil y horas estimadas |
| `Quotation Scope Item` | Copia congelada de un Scope Item dentro de una Quotation | Parent: `Quotation`; link a `Scope Item` y `Task` | Child table; `rate_locked` se fija en transición a En Revision |
| `Proposal Cost Matrix` | Costos por (Designation, Activity Type) | Alimenta freeze de costos en scope items | Rebuildeado diariamente; `is_general_rate=1` para filas de promedio por designación |
| `Proposal Cost Matrix Log` | Historial de cambios de tasa | Parent: ninguno | Append-only; creado por `cost_matrix.py` en cada cambio de tasa |
| `Quotation` (extendido) | Documento central; extendido con ~25 custom fields | Tiene child `Quotation Scope Item`; link a `Project` | Custom fields en fixture; extended class via `QuotationProposalMixin` |

---

## Integraciones externas

| Integración | Uso | Punto de entrada | Notas |
|---|---|---|---|
| ERPNext `Project` | Proyecto de ejecución creado desde propuesta ganada | `utils/project.py` — `create_project_from_quotation()` | ERPNext nativo; no se usa Project de Frappe base |
| ERPNext `Task` | Una tarea por scope item incluido en propuesta | `utils/project.py` — loop de scope_rows | Linked a `Quotation Scope Item.project_task` |
| ERPNext `Sales Order` | Hereda proyecto y cost center de la propuesta | `utils/sales_order.py` — hooks de validate y on_submit | El SO se crea nativamente; el app solo propaga campos |
| ERPNext `Activity Type` | Costing rate de fallback en ausencia de Activity Cost | `utils/cost_matrix.py` — `get_designation_cost()` | Tercer nivel de fallback en jerarquía de costos |
| HRMS `Salary Structure Assignment` | Proxy salarial de costo por hora (base/160h) | `utils/cost_matrix.py` — `_fetch_salary_data()` | Última fuente en jerarquía; solo si HRMS instalado |
| `Employee` + `Activity Cost` | Fuente primaria de costos por designación | `utils/cost_matrix.py` — `_fetch_activity_cost_data()` | Primera fuente en jerarquía de costos |
| Frappe `File` | Almacenamiento de PDFs generados | `utils/quotation.py` — `attach_proposal_pdfs()` | PDF público: Propuesta Comercial; privado: Rentabilidad Estimada |
| Frappe Realtime | Notificación al cliente JS cuando PDFs están listos | `utils/quotation.py` — `frappe.publish_realtime()` | Evento: `erpnext_proposals_pdfs_attached` |

---

## Permisos y workflows

| Área | Roles | Regla crítica | Implementación |
|---|---|---|---|
| Crear propuesta (Quotation) | Proposals User, Proposals Manager | `proposal_group` es obligatorio al insertar | `utils/quotation.py:before_insert` |
| Avanzar workflow (Borrador → En Revision) | Proposals User, Proposals Manager | Requiere template, cost center y total > 0 | `utils/workflow_validations.py:_validate_blocking` |
| Aprobar / Rechazar | Proposals Manager | Proposals User no puede aprobar ni rechazar | Fixture `workflow.json` — transición restringida por rol |
| Marcar como Ganada / Rechazar por Cliente | Proposals Manager | Solo desde "Enviada al Cliente" | Fixture `workflow.json` |
| Crear versión nueva | Proposals Manager, System Manager | Solo desde Rechazada sin proyecto activo | `utils/proposal_versioning.py:assert_can_manage_proposals()` + `assert_can_create_new_version()` |
| Crear proyecto | Proposals Manager, System Manager | Solo en estado Ganada, submitted, no superseded | `utils/project.py:assert_can_manage_proposals()` + `assert_can_create_project()` |
| Rebuild de costos | Proposals Manager, System Manager | Protegido en scheduler diario y endpoint manual | `utils/cost_matrix.py:assert_can_manage_proposals()` |
| Quotation declarar pérdida | Todos | Bloqueado si la Quotation tiene `proposal_group` | `overrides/quotation_override.py:declare_enquiry_lost` |
| Sales Order — botón visible | Todos | Solo aparece en estado Ganada + proyecto creado | `public/js/quotation.js` línea 14 |

---

## Workflow completo (fixture)

```
Borrador (docstatus=0)
    ↓ "Enviar a Revision" (Proposals User o Manager)
En Revision (docstatus=1) ← doc queda submitted aquí
    ↓ "Aprobar"               ↓ "Rechazar"
Aprobada (docstatus=1)    Rechazada (docstatus=1) ← terminal para esa versión
    ↓ "Enviar al Cliente"
Enviada al Cliente (docstatus=1)
    ↓ "Marcar como Ganada"    ↓ "Rechazar por Cliente"
Ganada (docstatus=1)      Rechazada (docstatus=1)
```

El submit automático ocurre en la transición Borrador → En Revision porque el estado
"En Revision" tiene `doc_status: "1"` en el fixture del workflow.

---

## Decisiones relacionadas

| ADR | Tema |
|---|---|
| [ADR-0000](../adr/0000-estado-inicial-app.md) | Estado inicial y arquitectura base del app |
| [ADR-0001](../adr/0001-mvp-etapa-1-implementacion.md) | Implementación MVP y scope del RC 1.0 |
| [ADR-0002](../adr/0002-rentabilidad-estimada-propuesta.md) | Diseño del reporte de rentabilidad estimada |
