# ADR-0020: Contrato económico canónico Project ↔ Quotations (autorizado vigente)

**Fecha:** 2026-09-12
**Status:** Aceptado
**Rama:** feat/project-authorized-economics → version-16
**Relacionado:** consume la Evaluación Económica ([ADR-0018](0018-evaluacion-economica-por-periodos.md)) como
fuente única de magnitudes; extiende el contrato de addendas ([ADR-0019](0019-aplicar-addendum-a-project-existente.md)).
Todo el bloque pertenece a `erpnext_proposals`; **`pmo` es consumidor posterior, nunca dependencia**.

## 1. Contexto

Una propuesta Ganada genera un Project; después pueden aplicarse addendas Ganadas al mismo Project.
`erpnext_proposals` debe responder de forma **canónica** el **autorizado vigente** del Project —ingreso,
costo, margen, costo laboral, costo externo— y mantener `Project.estimated_costing` sincronizado como
**espejo operacional** (la fuente histórica sigue siendo cada Quotation congelada). Sin depender de `pmo`
ni de `PMO Change Request.impact_amount`.

## 2. Decisión

**Módulo dedicado `utils/project_economics.py`** con la frontera de responsabilidades:
`project.py` orquesta (crear/materializar), `addendum.py` es identidad de addendas, `project_economics.py`
es el contrato económico Project ↔ Quotations.

- **`get_project_authorized_economics(project) -> dict`** (solo lectura):
  `Autorizado = Original(root) + Σ(addendas aplicadas)` por magnitud **independiente** (revenue, cost,
  margin, labor, external). `authorized_margin_pct` se **deriva** (`margin/revenue`), **nunca** se suma.
  Devuelve también `quotations` (auditoría de qué compone el autorizado) y `pending_changes` (addendas
  Ganadas del root aún no aplicadas — no suman). `financing_excluded = true`.
- **`sync_project_authorized_cost(project)`**: recomputa desde cero y espeja
  `Project.estimated_costing = authorized_cost` con `frappe.db.set_value(update_modified=False)` —**no**
  `save()`, para no disparar `update_costing` nativo (ERPNext sigue siendo autoridad de
  `total_costing_amount`/`total_purchase_cost`). Idempotente, sin flag `managed`, sin acumulación
  incremental; una edición manual de `estimated_costing` se corrige al siguiente sync.
- **Fuente económica ÚNICA por Quotation:** el motor de la Evaluación Económica (núcleo `_evaluate_doc`,
  que envuelve `get_economic_evaluation`). El módulo **no reimplementa** ninguna fórmula
  (horas·tarifa, recurrencia, costo externo, margen, financiamiento). El costo autorizado usa
  exclusivamente `totals.total_cost` (que **excluye** el financiamiento; éste es una capa aditiva aparte).
- **Costo autorizado sin financiamiento.** `totals.total_cost = labor + external`.

- **Resolución de la raíz (nunca por nombre ni heurística):** las Quotations con `docstatus=1` +
  `workflow_state="Ganada"` + no `superseded_by_proposal` + `proposal_project==project` + grupo **normal**
  (no addenda). Debe existir **exactamente una**; 0 o >1 = estado inconsistente → **fail-closed**.
- **Addendas aplicadas:** Ganada + submitted + no superseded + mismo root + `proposal_project==project`.
  La aplicación se decide por `proposal_project` (que fija `apply_addendum_to_project`), nunca por `pmo`.

- **Restricción de `apply_addendum_to_project` (contrato económico — cambio de #59):** SOLO acepta
  **addendas canónicas `ROOT-ADD-NN`**. Una Quotation de grupo normal ya **no** puede aplicarse a un
  Project existente. El modelo queda por construcción **`1 Project = 1 raíz + N addendas`**, que hace válido
  el invariante de raíz única. (`pmo` solo aplica addendas creadas con `create_addendum_quotation`, no se ve
  afectado.)

- **Integración transaccional (sin commit interno):**
  - `create_project_from_quotation`: validar → resolver/crear Project → materializar Tasks →
    **sincronizar `estimated_costing`** → `commit` existente. La sync ocurre **antes** del commit: un fallo
    económico no deja un Project económicamente incompleto.
  - `apply_addendum_to_project`: validar → materializar Tasks → fijar `proposal_project` →
    **recomputar autorizado y sincronizar** → devolver. La asociación se escribe **antes** del recompute
    (el helper identifica las addendas aplicadas por `proposal_project==project`). Sin commit interno: un
    fallo económico permite que la transacción externa de `pmo` revierta Tasks + asociación + `estimated_costing`.

### Invariante de congelamiento (defensa en profundidad)

Una propuesta **formal** (con `proposal_template`) que abandona Borrador queda **congelada** y **nunca**
opera con datos vivos. Validación **canónica única** `quotation.assert_economic_snapshot_complete(doc)`
(gate `proposal_template`, igual que `freeze_proposal`) reutilizada por:
1. `on_quotation_before_submit` — tras `freeze_proposal`, exige snapshot completo o el submit falla;
2. transiciones de workflow de propuestas ya submitted (excluida Borrador→En Revisión, que es la que
   congela y valida vía before_submit);
3. `project_economics` — antes de usar la economía de cada Quotation.

Requiere por línea: fila costable → `rate_locked`; Item vendido → `proposal_cost_locked` +
`proposal_economic_behavior`; Required → `cost_locked` + `economic_behavior`. Si falta algo → **fail-closed**
(no se reconstruye con Cost Matrix / precios / Proposal Settings actuales). **Corrección incluida:**
`rate_locked=1` con `costing_rate=0` es un congelamiento **válido** (un 0 legítimo) — antes reconsultaba la
Cost Matrix vigente; se alinean `economic_calendar._labor_rate_source` **y** `profitability_estimate`.

### Moneda v1 (sin FX)

Ruta soportada: `Quotation.currency == Company.default_currency` y `conversion_rate` compatible con 1, en
root y en cada addenda aplicada. Si algo lo viola → la sincronización **falla cerrada**; no se convierte ni
se mezclan monedas. La normalización multidivisa es un cambio posterior explícito del motor.

## 3. Consecuencias

- `pmo` puede presentar **Autorizado → Ordenado → Facturado** consumiendo esta primitiva
  (`Project.total_sales_amount`/`total_billed_amount` siguen siendo nativos de ERPNext; el costo real
  también). `authorized_revenue` **no** se persiste en un campo de Project.
- `estimated_costing` es un espejo derivado y determinista; deja de ser editable como fuente autorizada.
- El invariante de congelamiento queda **validado**, no asumido: protege contra corrupción, `db.set_value`
  privilegiado, scripts y regresiones futuras del freeze.
- Sin migración/backfill/patches: `erpnext_proposals` no está en producción; el diseño asume el contrato
  normal (congelar al salir de Borrador).

## 4. Alternativas descartadas

- **Aplicar Quotations normales como "cambios"** (mantener #59 genérico): dos propuestas normales por
  Project son indistinguibles → la raíz no se puede resolver. Descartada a favor de `1 raíz + N addendas`.
- **Marcar el root con un flag/campo nuevo:** más invasivo; reintroduce ambigüedad. Descartada.
- **Reimplementar las fórmulas económicas en el helper:** duplicaría la lógica del motor. Se usa el motor
  como fuente única (núcleo `_evaluate_doc`; se evita el gate de permiso HTTP del wrapper porque la sync es
  derivación de sistema autorizada por WRITE sobre el Project).
- **Normalización FX en este bloque:** fuera de alcance; se falla cerrado ante moneda incompatible.
