<!--
  ARCHIVO GENERADO AUTOMÁTICAMENTE. NO EDITAR MANUALMENTE.
  Regenerar con: python3 scripts/generate_reference.py
  Fecha generación: 2026-09-01 23:55
-->


# Referencia — API

Funciones expuestas como endpoints HTTP via `@frappe.whitelist()`.
Accesibles desde el cliente JS con `frappe.call({method: '...'})` o desde Python con `frappe.get_attr('...')`.


## Índice

- **erpnext_proposals/erpnext_proposals/utils/cost_matrix.py**
  - [`rebuild_cost_matrix`](#rebuild-cost-matrix)
- **erpnext_proposals/erpnext_proposals/utils/print_format.py**
  - [`get_proposal_print_formats`](#get-proposal-print-formats)
  - [`get_print_format_status`](#get-print-format-status)
  - [`get_effective_commercial_print_format`](#get-effective-commercial-print-format)
  - [`download_commercial_draft_pdf`](#download-commercial-draft-pdf)
  - [`get_effective_sow_print_format`](#get-effective-sow-print-format)
  - [`download_sow_draft_pdf`](#download-sow-draft-pdf)
  - [`download_rentabilidad_draft_pdf`](#download-rentabilidad-draft-pdf)
- **erpnext_proposals/erpnext_proposals/utils/project.py**
  - [`create_project_from_quotation`](#create-project-from-quotation)
- **erpnext_proposals/erpnext_proposals/utils/proposal_versioning.py**
  - [`create_new_proposal_version`](#create-new-proposal-version)
- **erpnext_proposals/erpnext_proposals/utils/quotation.py**
  - [`resync_scope_from_catalog`](#resync-scope-from-catalog)
  - [`add_missing_scope_items_from_items`](#add-missing-scope-items-from-items)
  - [`get_template_optional_sections`](#get-template-optional-sections)
  - [`get_proposal_documents_status`](#get-proposal-documents-status)
- **erpnext_proposals/erpnext_proposals/utils/scope_item_links.py**
  - [`get_scope_items_for_item`](#get-scope-items-for-item)
  - [`set_scope_items_for_item`](#set-scope-items-for-item)


---


## `erpnext_proposals/erpnext_proposals/utils/cost_matrix.py`


### `rebuild_cost_matrix()`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.cost_matrix`

Rebuilds Proposal Cost Matrix from employee cost data.


## `erpnext_proposals/erpnext_proposals/utils/print_format.py`


### `get_proposal_print_formats(doctype, txt, searchfield, start, page_len, filters)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.print_format`

Query central del campo Link para elegir el Print Format de una propuesta.


### `get_print_format_status(pf_name)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.print_format`

Estado de elegibilidad de un Print Format referenciado (para el warning del cliente).


### `get_effective_commercial_print_format(quotation)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.print_format`

Formato comercial efectivo de una Quotation (usado por el botón de impresión en JS).


### `download_commercial_draft_pdf(quotation)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.print_format`

Descarga un PDF **BORRADOR** (no oficial) de la Propuesta Comercial, para revisión externa


### `get_effective_sow_print_format(quotation)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.print_format`

Print Format SOW efectivo de una Quotation (o vacío si la plantilla no define SOW). Lo usa el JS


### `download_sow_draft_pdf(quotation)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.print_format`

Descarga un PDF **BORRADOR** del SOW mientras la Quotation sigue editable. Mismo mecanismo que


### `download_rentabilidad_draft_pdf(quotation)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.print_format`

Descarga un PDF **BORRADOR** de la Rentabilidad Estimada mientras la Quotation sigue editable.


## `erpnext_proposals/erpnext_proposals/utils/project.py`


### `create_project_from_quotation(quotation_name)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.project`


## `erpnext_proposals/erpnext_proposals/utils/proposal_versioning.py`


### `create_new_proposal_version(quotation_name, reason, summary)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.proposal_versioning`

Create a new proposal version from a Rejected submitted Quotation.


## `erpnext_proposals/erpnext_proposals/utils/quotation.py`


### `resync_scope_from_catalog(quotation_name)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.quotation`

Sincroniza explícitamente la tabla de alcance con el catálogo Scope Item.


### `add_missing_scope_items_from_items(quotation_name)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.quotation`

Acción MANUAL explícita: revisa TODOS los Items actuales de la Quotation y agrega únicamente las


### `get_template_optional_sections(template)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.quotation`

Secciones OPCIONALES de un Proposal Template para el selector `proposal_optional_sections`.


### `get_proposal_documents_status(quotation)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.quotation`

Comprobación REAL de que los documentos oficiales de la propuesta ya fueron generados/adjuntados.


## `erpnext_proposals/erpnext_proposals/utils/scope_item_links.py`


### `get_scope_items_for_item(item)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.scope_item_links`

Scope Items asociados a un Item (child + legacy) para el diálogo desde el formulario Item.


### `set_scope_items_for_item(item, scope_items)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.scope_item_links`

Guarda la selección de Scope Items para UN Item (edición explícita del usuario, no migración):
