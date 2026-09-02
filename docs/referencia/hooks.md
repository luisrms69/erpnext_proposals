<!--
  ARCHIVO GENERADO AUTOMÁTICAMENTE. NO EDITAR MANUALMENTE.
  Regenerar con: python3 scripts/generate_reference.py
  Fecha generación: 2026-09-02 15:32
-->


# Referencia — Hooks

Hooks activos en el app. Fuente: `hooks.py`.


## doc_events

| DocType | Evento | Handler |
|---|---|---|
| `File` | `on_trash` | `protect_official_document_on_trash` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.official_document_protection.protect_official_document_on_trash` |
| `Print Format` | `validate` | `protect_historical_print_format_on_save` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.print_format_protection.protect_historical_print_format_on_save` |
| `Print Format` | `on_trash` | `protect_historical_print_format_on_trash` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.print_format_protection.protect_historical_print_format_on_trash` |
| `Print Format` | `before_rename` | `protect_historical_print_format_on_rename` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.print_format_protection.protect_historical_print_format_on_rename` |
| `Quotation` | `before_insert` | `on_quotation_before_insert` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.quotation.on_quotation_before_insert` |
| `Quotation` | `before_insert` | `set_proposal_contact` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.quotation_contact.set_proposal_contact` |
| `Quotation` | `before_validate` | `apply_fiscal_taxes` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.quotation_tax.apply_fiscal_taxes` |
| `Quotation` | `validate` | `on_quotation_validate` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.quotation.on_quotation_validate` |
| `Quotation` | `validate` | `on_quotation_validate_workflow` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.workflow_validations.on_quotation_validate_workflow` |
| `Quotation` | `validate` | `autocorrect_missing_contact` |
|  |  | `erpnext_proposals.erpnext_proposals.utils.quotation_contact.autocorrect_missing_contact` |
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
