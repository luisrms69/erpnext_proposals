<!--
  ARCHIVO GENERADO AUTOMÁTICAMENTE. NO EDITAR MANUALMENTE.
  Regenerar con: python3 scripts/generate_reference.py
  Fecha generación: 2026-07-15 15:38
-->


# Referencia — DocTypes

DocTypes del app organizados por módulo. Incluye campos activos (excluye Section Break, Column Break, HTML).


## ERPNext Proposals


### Proposal Cost Matrix

Fuente: `erpnext_proposals/erpnext_proposals/doctype/proposal_cost_matrix/proposal_cost_matrix.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `designation` | Designation | Link | ✅ | Designation |
| `activity_type` | Tipo de Actividad | Link |  | Activity Type |
| `is_general_rate` | Es Tasa General | Check |  |  |
| `avg_costing_rate` | Costo/hora Promedio | Currency |  |  |
| `avg_billing_rate` | Precio/hora Promedio | Currency |  |  |
| `employee_count` | Empleados | Int |  |  |
| `source` | Fuente | Select |  | … |
| `status` | Estado | Select |  | … |
| `last_updated` | Última Actualización | Datetime |  |  |
| `rate_changed_on` | Última Variación | Datetime |  |  |
| `notes` | Notas | Small Text |  |  |


### Proposal Cost Matrix Log

Fuente: `erpnext_proposals/erpnext_proposals/doctype/proposal_cost_matrix_log/proposal_cost_matrix_log.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `designation` | Designation | Link | ✅ | Designation |
| `activity_type` | Tipo de Actividad | Link |  | Activity Type |
| `is_general_rate` | Es Tasa General | Check |  |  |
| `old_rate` | Tasa Anterior | Currency |  |  |
| `new_rate` | Tasa Nueva | Currency |  |  |
| `source` | Fuente | Data |  |  |
| `employee_count` | Empleados | Int |  |  |
| `changed_on` | Fecha del cambio | Datetime |  |  |
| `rebuild_run_id` | Rebuild Run ID | Data |  |  |
| `notes` | Notas | Small Text |  |  |


### Proposal Phase

Fuente: `erpnext_proposals/erpnext_proposals/doctype/proposal_phase/proposal_phase.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `phase_code` | Phase Code | Data | ✅ |  |
| `phase_name` | Phase Name | Data | ✅ |  |
| `sequence` | Sequence | Int | ✅ |  |
| `enabled` | Enabled | Check |  |  |


### Proposal Section

Fuente: `erpnext_proposals/erpnext_proposals/doctype/proposal_section/proposal_section.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `section_name` | Section Name | Data | ✅ |  |
| `is_executive_summary` | Es Resumen Ejecutivo | Check |  |  |
| `title` | Display Title | Data |  |  |
| `enabled` | Enabled | Check |  |  |
| `content` | Content | Text Editor |  |  |


### Proposal Template

Fuente: `erpnext_proposals/erpnext_proposals/doctype/proposal_template/proposal_template.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `template_name` | Template Name | Data | ✅ |  |
| `description` | Description | Small Text |  |  |
| `sections` | Sections | Table |  | Proposal Template Section |


### Proposal Template Section _Child table_

Fuente: `erpnext_proposals/erpnext_proposals/doctype/proposal_template_section/proposal_template_section.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `sequence` | Sequence | Int |  |  |
| `proposal_section` | Proposal Section | Link | ✅ | Proposal Section |
| `custom_title` | Custom Title | Data |  |  |
| `include_by_default` | Include by Default | Check |  |  |
| `use_custom_content` | Use Custom Content | Check |  |  |
| `custom_content` | Custom Content | Text Editor |  |  |


### Quotation Scope Item _Child table_

Fuente: `erpnext_proposals/erpnext_proposals/doctype/quotation_scope_item/quotation_scope_item.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `scope_item` | Scope Item | Link |  | Scope Item |
| `item_code` | Item Code | Data |  |  |
| `sequence` | Seq | Int |  |  |
| `auto_generated` | Auto Generated | Check |  |  |
| `code` | Code | Data |  |  |
| `title` | Title | Data |  |  |
| `include_in_proposal` | Include in Proposal | Check |  |  |
| `description` | Description | Text Editor |  |  |
| `deliverable` | Deliverable | Text Editor |  |  |
| `phase` | Phase | Link |  | Proposal Phase |
| `erpnext_item` | ERPNext Item (deprecated) | Link |  | Item |
| `estimated_hours` | Estimated Hours | Float |  |  |
| `activity_type` | Activity Type | Link |  | Activity Type |
| `designation` | Designation | Link |  | Designation |
| `project_task` | Project Task | Link |  | Task |
| `costing_rate` | Tasa de costo | Currency |  |  |
| `rate_source` | Fuente de tasa | Data |  |  |
| `rate_locked` | Costo congelado | Check |  |  |
| `rate_locked_on` | Congelado el | Datetime |  |  |


### Scope Item

Fuente: `erpnext_proposals/erpnext_proposals/doctype/scope_item/scope_item.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `code` | Code | Data | ✅ |  |
| `sequence` | Sequence | Int |  |  |
| `title` | Title | Data | ✅ |  |
| `enabled` | Enabled | Check |  |  |
| `visible_in_proposal` | Visible in Proposal | Check |  |  |
| `description` | Description | Text Editor |  |  |
| `deliverable` | Deliverable | Text Editor |  |  |
| `phase` | Phase | Link |  | Proposal Phase |
| `erpnext_item` | ERPNext Item | Link |  | Item |
| `estimated_hours` | Estimated Hours | Float |  |  |
| `default_activity_type` | Default Activity Type | Link |  | Activity Type |
| `default_designation` | Default Designation | Link |  | Designation |
