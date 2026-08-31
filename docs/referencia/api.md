<!--
  ARCHIVO GENERADO AUTOMÁTICAMENTE. NO EDITAR MANUALMENTE.
  Regenerar con: python3 scripts/generate_reference.py
  Fecha generación: 2026-07-30 21:45
-->


# Referencia — API

Funciones expuestas como endpoints HTTP via `@frappe.whitelist()`.
Accesibles desde el cliente JS con `frappe.call({method: '...'})` o desde Python con `frappe.get_attr('...')`.


## Índice

- **erpnext_proposals/erpnext_proposals/utils/cost_matrix.py**
  - [`rebuild_cost_matrix`](#rebuild-cost-matrix)
- **erpnext_proposals/erpnext_proposals/utils/print_format.py**
  - [`get_effective_commercial_print_format`](#get-effective-commercial-print-format)
  - [`download_commercial_pdf`](#download-commercial-pdf)
- **erpnext_proposals/erpnext_proposals/utils/project.py**
  - [`create_project_from_quotation`](#create-project-from-quotation)
- **erpnext_proposals/erpnext_proposals/utils/proposal_versioning.py**
  - [`create_new_proposal_version`](#create-new-proposal-version)
- **erpnext_proposals/erpnext_proposals/utils/quotation.py**
  - [`resync_scope_from_catalog`](#resync-scope-from-catalog)


---


## `erpnext_proposals/erpnext_proposals/utils/cost_matrix.py`


### `rebuild_cost_matrix()`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.cost_matrix`

Rebuilds Proposal Cost Matrix from employee cost data.


## `erpnext_proposals/erpnext_proposals/utils/print_format.py`


### `get_effective_commercial_print_format(quotation)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.print_format`

Formato comercial efectivo de una Quotation (helper de UI para mostrar el *"Formato efectivo actual"*; no genera el PDF).


### `download_commercial_pdf(quotation)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.print_format`

Descarga el PDF comercial de una Quotation. Lo invoca el botón *Imprimir Propuesta Comercial* (JS).

- **Argumento:** `quotation` — nombre de la Quotation.
- **Permiso requerido:** lectura (`read`) sobre la Quotation.
- **Comportamiento:** resuelve el Print Format efectivo en servidor (`resolve_commercial_print_format`)
  y genera los bytes **exclusivamente** con `render_proposal_pdf()`, respetando el renderer profile
  (`gotenberg-v1` o `legacy`, ver **ADR-0015**). No construye `/printview` ni llama al motor directo.
- **Respuesta:** descarga del archivo (`type="download"`, `content_type="application/pdf"`,
  `filename="<Quotation>.pdf"`). Es preview/descarga: **no** adjunta el PDF como documento oficial.


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
