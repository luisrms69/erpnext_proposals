<!--
  ARCHIVO GENERADO AUTOMÁTICAMENTE. NO EDITAR MANUALMENTE.
  Regenerar con: python3 scripts/generate_reference.py
  Fecha generación: 2026-07-14 16:59
-->


# Referencia — Hooks

Hooks activos en el app. Fuente: `hooks.py`.


## doc_events

| DocType | Evento | Handler |
|---|---|---|
| `Quotation` | `before_insert` | `on_quotation_before_insert` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.quotation.on_quotation_before_insert` |
| `Quotation` | `validate` | `on_quotation_validate` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.quotation.on_quotation_validate` |
| `Quotation` | `validate` | `on_quotation_validate_workflow` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.workflow_validations.on_quotation_validate_workflow` |
| `Quotation` | `before_submit` | `on_quotation_before_submit` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.quotation.on_quotation_before_submit` |
| `Quotation` | `before_update_after_submit` | `on_quotation_validate_workflow` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.workflow_validations.on_quotation_validate_workflow` |
| `Quotation` | `before_update_after_submit` | `on_quotation_before_update_after_submit` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.quotation.on_quotation_before_update_after_submit` |
| `Sales Order` | `validate` | `on_sales_order_validate` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.sales_order.on_sales_order_validate` |
| `Sales Order` | `on_submit` | `on_sales_order_submit` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.sales_order.on_sales_order_submit` |


## fixtures

Fixtures exportados con `bench export-fixtures`:

- `{'doctype': 'Custom Field'}`
- `{'doctype': 'Role'}`
- `{'doctype': 'Workflow'}`
- `{'doctype': 'Workflow State'}`
