# ADR-0021: Versionado de propuesta — herencia por defecto del estado comercial

**Fecha:** 2026-09-21 · **Status:** Cerrado — vigente
**Rama:** feat/versioning-inherit-commercial-fields → version-16

---

## Contexto

`create_new_proposal_version()` construía la nueva versión (V2, V3…) con un **diccionario explícito**
de campos. Ese allowlist se desactualizó y **descartaba silenciosamente** avance comercial real de la
versión anterior: `crm_deal` (rompía el vínculo con Frappe CRM), `contact_person`, `valid_till`,
`taxes_and_charges` y filas de impuesto, `tc_name`/`terms`, direcciones, `proposal_contract_term_months`,
`proposal_financing_*`, `proposal_optional_sections`, y el Payment Schedule manual (que además abortaba
con un `throw`). El usuario debía rehacer la propuesta desde CRM, perdiendo todo ese trabajo.

## Decisión

El conjunto a copiar se **deriva de la metadata** (`frappe.get_meta`), no de una lista a mano. Regla de
negocio: **una nueva versión conserva por defecto TODO el contenido comercial**; solo se excluye,
resetea o recalcula lo que tenga una razón demostrable.

Para el padre (`Quotation`) y cada child table gestionada, se copia cada campo de valor con
`no_copy == 0` que **no** esté en `EXCLUDE[doctype]`, más `FORCE_INCLUDE` (campos `no_copy=1` que sí
queremos), y luego se aplican los `TRANSFORM`. Cualquier campo nuevo se hereda por defecto; las
excepciones se enumeran explícitamente. Un **test de cobertura meta-driven** falla si un campo queda
sin clasificar (impide regresiones silenciosas).

### Categorías de exclusión (única razón para NO heredar)

- **Identidad del nuevo documento:** `name`, `docstatus`, `amended_from`, `naming_series`,
  `transaction_date`→hoy.
- **Workflow / ciclo de vida:** `workflow_state`→Borrador, `status`; revisión/aprobación de la
  versión anterior.
- **Cadena de versiones:** `proposal_version`→N+1, `previous_proposal`→anterior,
  `superseded_by_proposal`→∅, `proposal_revision_reason/summary`→de la revisión.
- **Artefactos downstream:** `proposal_project`→∅, Scope `project_task`→∅.
- **Snapshots/frozen (re-congelar al re-formalizar; ADR-0017/0018/0019):** frozen de Quotation Item
  (`no_copy=1`), de Proposal Required Item y de Quotation Scope Item (deny-list explícita porque **no**
  están marcados `no_copy`), `proposal_effective_print_format` (se hereda el override
  `proposal_print_format`).
- **Cálculos técnicos derivados:** montos computados de impuestos; procedencia de scope
  (`source_type/source_row`).

### Reglas especiales

- **`valid_till`:** se hereda **literal** si sigue vigente contra la nueva `transaction_date`. ERPNext
  prohíbe nativamente `valid_till < transaction_date` en cada save (incluido Borrador,
  `validate_valid_till`); si la fecha heredada ya venció, se deja **en blanco** (no se inventa una
  nueva) para no impedir la creación de la Draft.
- **`contact_person`:** se hereda. El hook `set_proposal_contact` (autoritativo en la creación
  inicial Deal→Quotation) **no** re-decide el contacto cuando el documento viene del versionado con un
  `contact_person` ya heredado (respeta `flags.from_proposal_versioning`).
- **Payment Schedule:** con Payment Terms Template se hereda el template y ERPNext regenera lo
  derivado; **manual** se preservan las filas (términos, porcentajes, descripciones, fechas), sin
  `throw`.
- **`proposal_sections_snapshot`:** `FORCE_INCLUDE` (copia literal pese a `no_copy=1`).

## Consecuencias

- V2/V3 conservan el avance comercial de V1; se elimina la clase de bug de "campo perdido en el
  versionado", incluso para campos futuros (gracias al test de cobertura).
- El contrato externo de `create_new_proposal_version(quotation_name, reason, summary)` no cambia.
- La cadena de versiones, los guards de "una sola propuesta viva por grupo" y el re-freeze de
  snapshots se conservan intactos.

## Alternativas descartadas

- **Parche puntual para `crm_deal`:** no cubre los demás campos perdidos ni escenarios futuros.
- **`frappe.copy_doc` puro:** respeta `no_copy` pero **filtraría** los frozen de Required/Scope Item
  (no marcados `no_copy`), rompiendo los guards económicos; por eso se usa allowlist-builder + deny-list.
