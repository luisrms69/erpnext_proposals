<!--
  ARCHIVO GENERADO AUTOMÁTICAMENTE. NO EDITAR MANUALMENTE.
  Regenerar con: python3 scripts/generate_reference.py
  Fecha generación: 2026-09-02 21:50
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


### Proposal Economic Behavior Rule _Child table_

Fuente: `erpnext_proposals/erpnext_proposals/doctype/proposal_economic_behavior_rule/proposal_economic_behavior_rule.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `source_type` | Aplicar a | Select | ✅ | Item… |
| `source` | Item / Item Group | Dynamic Link | ✅ | source_type |
| `economic_behavior` | Comportamiento económico | Select | ✅ | one_time… |
| `interval` | Intervalo | Select |  | … |
| `interval_count` | Cada N intervalos | Int |  |  |


### Proposal Optional Section _Child table_

Fuente: `erpnext_proposals/erpnext_proposals/doctype/proposal_optional_section/proposal_optional_section.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `proposal_section` | Proposal Section | Link | ✅ | Proposal Section |


### Proposal Phase

Fuente: `erpnext_proposals/erpnext_proposals/doctype/proposal_phase/proposal_phase.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `phase_code` | Phase Code | Data | ✅ |  |
| `phase_name` | Phase Name | Data | ✅ |  |
| `sequence` | Sequence | Int | ✅ |  |
| `enabled` | Enabled | Check |  |  |


### Proposal Required Item _Child table_

Fuente: `erpnext_proposals/erpnext_proposals/doctype/proposal_required_item/proposal_required_item.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `item` | Item | Link | ✅ | Item |
| `qty` | Qty | Float | ✅ |  |
| `uom` | Unidad | Link |  | UOM |
| `auto_generated` | Auto Generated | Check |  |  |
| `frozen_cost_rate` | Costo de compra (guardado) | Currency |  |  |
| `frozen_cost_source` | Origen del costo | Data |  |  |
| `cost_locked` | Costo ya guardado | Check |  |  |
| `economic_behavior` | Comportamiento económico (congelado) | Data |  |  |
| `billing_interval` | Intervalo de recurrencia (congelado) | Data |  |  |
| `billing_interval_count` | Conteo de intervalo (congelado) | Int |  |  |


### Proposal Required Item Rule _Child table_

Fuente: `erpnext_proposals/erpnext_proposals/doctype/proposal_required_item_rule/proposal_required_item_rule.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `source_type` | Aplicar a | Select | ✅ | Item… |
| `source` | Item / Item Group | Dynamic Link | ✅ | source_type |
| `required_item` | Item requerido | Link | ✅ | Item |


### Proposal Section

Fuente: `erpnext_proposals/erpnext_proposals/doctype/proposal_section/proposal_section.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `section_name` | Section Name | Data | ✅ |  |
| `is_executive_summary` | Es Resumen Ejecutivo | Check |  |  |
| `title` | Display Title | Data |  |  |
| `enabled` | Enabled | Check |  |  |
| `content` | Content | Text Editor |  |  |


### Proposal Settings

Fuente: `erpnext_proposals/erpnext_proposals/doctype/proposal_settings/proposal_settings.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `company` | Compañía | Link | ✅ | Company |
| `required_item_rules` | Reglas Item / Item Group → Items requeridos | Table |  | Proposal Required Item Rule |
| `default_procurement_scope_item` | Scope Item de abastecimiento por defecto | Link |  | Scope Item |
| `economic_behavior_rules` | Comportamiento económico por Item / Item Group | Table |  | Proposal Economic Behavior Rule |
| `default_contract_term_months` | Plazo contractual por defecto (meses) | Int |  |  |


### Proposal Template

Fuente: `erpnext_proposals/erpnext_proposals/doctype/proposal_template/proposal_template.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `template_name` | Template Name | Data | ✅ |  |
| `description` | Description | Small Text |  |  |
| `print_format` | Print Format | Link |  | Print Format |
| `sow_print_format` | SOW Print Format | Link |  | Print Format |
| `letter_head` | Letter Head | Link |  | Letter Head |
| `separate_cover_page` | Portada separada (2 renders + merge) | Check |  |  |
| `sections` | Sections | Table |  | Proposal Template Section |


### Proposal Template Section _Child table_

Fuente: `erpnext_proposals/erpnext_proposals/doctype/proposal_template_section/proposal_template_section.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `sequence` | Sequence | Int |  |  |
| `proposal_section` | Proposal Section | Link | ✅ | Proposal Section |
| `custom_title` | Custom Title | Data |  |  |
| `hide_title` | Hide Title | Check |  |  |
| `page_break_before` | Page Break Before | Check |  |  |
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
| `is_internal_cost_task` | Tarea interna de costo | Check |  |  |
| `description` | Description | Text Editor |  |  |
| `deliverable` | Deliverable | Text Editor |  |  |
| `phase` | Phase | Link |  | Proposal Phase |
| `erpnext_item` | ERPNext Item (deprecated) | Link |  | Item |
| `estimated_hours` | Estimated Hours | Float |  |  |
| `activity_type` | Activity Type | Link |  | Activity Type |
| `designation` | Designation | Link |  | Designation |
| `project_task` | Project Task | Link |  | Task |
| `planned_start_offset_days` | Planned Start Offset (days) | Data |  |  |
| `moment` | Moment | Data |  |  |
| `planned_duration_days` | Planned Duration (days) | Int |  |  |
| `is_milestone` | Is Milestone | Check |  |  |
| `dependency_scope_item_codes` | Dependency Scope Item Codes | Small Text |  |  |
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
| `is_internal_cost_task` | Tarea interna de costo | Check |  |  |
| `description` | Description | Text Editor |  |  |
| `deliverable` | Deliverable | Text Editor |  |  |
| `phase` | Phase | Link |  | Proposal Phase |
| `erpnext_item` | ERPNext Item | Link |  | Item |
| `erpnext_items` | ERPNext Items | Table |  | Scope Item ERPNext Item |
| `estimated_hours` | Estimated Hours | Float |  |  |
| `default_activity_type` | Default Activity Type | Link |  | Activity Type |
| `default_designation` | Default Designation | Link |  | Designation |
| `planned_start_offset_days` | Planned Start Offset (days) | Data |  |  |
| `moment` | Moment | Data |  |  |
| `planned_duration_days` | Planned Duration (days) | Int |  |  |
| `is_milestone` | Is Milestone | Check |  |  |
| `depends_on_scope_items` | Depends On (Scope Items) | Table |  | Scope Item Dependency |


### Scope Item Dependency _Child table_

Fuente: `erpnext_proposals/erpnext_proposals/doctype/scope_item_dependency/scope_item_dependency.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `depends_on` | Depends On | Link | ✅ | Scope Item |


### Scope Item ERPNext Item _Child table_

Fuente: `erpnext_proposals/erpnext_proposals/doctype/scope_item_erpnext_item/scope_item_erpnext_item.json`


| Campo | Label | Tipo | Requerido | Opciones |
|---|---|---|---|---|
| `item` | Item | Link | ✅ | Item |
