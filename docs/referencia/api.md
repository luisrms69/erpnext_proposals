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
  - [`download_commercial_draft_pdf`](#download-commercial-draft-pdf)
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

Resuelve y devuelve el Print Format comercial **efectivo** de una Quotation (congelada → el congelado;
Borrador → resolución dinámica). Valida permiso de lectura. Lo usa el botón *Imprimir Propuesta
Comercial* (JS): con el nombre devuelto abre la **vista preliminar** `/printview` (revisión HTML). No
genera ni descarga un PDF.


### `download_commercial_draft_pdf(quotation)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.print_format`

Descarga un PDF **BORRADOR** (no oficial) de la Propuesta Comercial, para revisión externa mientras la
Quotation sigue en Borrador. Lo invoca el botón *Descargar PDF Borrador* (JS), disponible solo en Borrador.

- **Argumento:** `quotation` — nombre de la Quotation.
- **Permiso requerido:** lectura (`read`) sobre la Quotation.
- **Comportamiento:** resuelve el Print Format efectivo en servidor (`resolve_commercial_print_format`)
  y genera los bytes **exclusivamente** con `render_proposal_pdf()`, respetando el renderer profile
  (`gotenberg-v1` o `legacy`, ver **ADR-0015**). **No** adjunta el PDF ni crea File, **no** congela,
  **no** cambia `workflow_state`, **no** hace submit y **no** invoca `attach_proposal_pdfs` (el documento
  formal se genera aparte al pasar a *En Revisión*).
- **Respuesta:** descarga del archivo (`type="download"`, `content_type="application/pdf"`,
  `filename="BORRADOR - Propuesta Comercial - <Quotation>.pdf"`) — el prefijo `BORRADOR` lo distingue del
  documento oficial.


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
