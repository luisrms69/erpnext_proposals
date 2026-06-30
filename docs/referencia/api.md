<!--
  ARCHIVO GENERADO AUTOMÁTICAMENTE. NO EDITAR MANUALMENTE.
  Regenerar con: python3 scripts/generate_reference.py
  Fecha generación: 2026-06-29 22:52
-->


# Referencia — API

Funciones expuestas como endpoints HTTP via `@frappe.whitelist()`.
Accesibles desde el cliente JS con `frappe.call({method: '...'})` o desde Python con `frappe.get_attr('...')`.


## Índice

- **erpnext_proposals/erpnext_proposals/utils/cost_matrix.py**
  - [`rebuild_cost_matrix`](#rebuild-cost-matrix)
- **erpnext_proposals/erpnext_proposals/utils/project.py**
  - [`create_project_from_quotation`](#create-project-from-quotation)
- **erpnext_proposals/erpnext_proposals/utils/proposal_versioning.py**
  - [`create_new_proposal_version`](#create-new-proposal-version)


---


## `erpnext_proposals/erpnext_proposals/utils/cost_matrix.py`


### `rebuild_cost_matrix()`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.cost_matrix`

Rebuilds Proposal Cost Matrix from employee cost data.


## `erpnext_proposals/erpnext_proposals/utils/project.py`


### `create_project_from_quotation(quotation_name)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.project`


## `erpnext_proposals/erpnext_proposals/utils/proposal_versioning.py`


### `create_new_proposal_version(quotation_name, reason, summary)`

**Módulo:** `erpnext_proposals.erpnext_proposals.utils.proposal_versioning`

Create a new proposal version from a Rejected submitted Quotation.
