# ADR-0008 — Integración fiscal de Quotation por reutilización read-only de `facturacion_mexico`

**Estado:** Aceptado · **Fecha:** 2026-07-30

## Contexto

`facturacion_mexico` resuelve y aplica impuestos automáticamente **solo en Sales Invoice**
(`before_validate`): a partir del Customer obtiene su Centro de Costos por defecto, deriva la
**Oficina Fiscal / Branch** (mapeo 1:1 Cost Center → Branch), determina la **zona** (Nacional/Frontera)
y la **variante** por clasificación de items (Básico/IEPS/Retenciones/Total), y selecciona el
**Sales Taxes and Charges Template (STCT)** por convención de nombre `IVA {zona} - {variante} - {abbr}`.

La **Quotation** comercial no recibía esa resolución: `facturacion_mexico` no engancha Quotation, así
que las propuestas se generaban sin impuestos automáticos aunque la configuración fiscal estuviera
completa. El requisito es que la Quotation comercial muestre los mismos impuestos que terminará
teniendo el Sales Invoice, **sin modificar** `facturacion_mexico` (app en producción cuyo flujo de
Sales Invoice debe permanecer intacto).

## Decisión

Se implementa un **adapter exclusivamente en `erpnext_proposals`**
(`erpnext_proposals/utils/quotation_tax.py`), enganchado a `Quotation.before_validate`, que
**reutiliza por importación** los helpers de *resolución* de `facturacion_mexico` **sin modificarlos**:

- `_get_customer_default_cc`, `_get_branch_from_cost_center`, `_get_border_zone_status`,
  `_determinar_variante_stct`, `_find_stct_by_variant`.

La *aplicación* final del template se hace en `erpnext_proposals` con el nativo de ERPNext
`erpnext.controllers.accounts_controller.get_taxes_and_charges` (se fija `taxes_and_charges` y se
recargan las filas de `taxes`).

Reglas del adapter:

- **`facturacion_mexico` NO se modifica** (ni código, ni hooks, ni handlers, ni validaciones, ni el
  flujo de Sales Invoice). La reutilización es solo por `import` de funciones puras de lectura.
- Solo aplica cuando **`quotation_to == "Customer"`** (no CRM Deal / Lead / Prospect).
- Usa **`proposal_cost_center`** (Custom Field de `erpnext_proposals`) o, si está vacío, el Centro de
  Costos por defecto del Customer; y a partir de él la configuración fiscal existente
  **CC → Branch → zona → STCT**.
- **No-op suave**: si no puede resolver la configuración fiscal (sin Centro de Costos, sin Branch
  mapeada, sin zona definida o sin STCT), **no hace nada y no bloquea** el guardado de la Quotation.
- **Respeta la selección manual**: si `taxes_and_charges` ya tiene valor, **no lo sobrescribe**.
- **NO** se importa `_set_stct_by_branch` (que bloquea con `frappe.throw` y emite `msgprint`); por eso
  la Quotation nunca se bloquea por configuración fiscal faltante.
- **No** aplica la validación SAT estricta de Sales Invoice (clave SAT obligatoria por línea, Centro de
  Costos obligatorio): esa validación es propia del flujo de facturación y no se replica en la cotización.

## Consecuencias

- La Quotation comercial (`quotation_to == "Customer"`) obtiene automáticamente el mismo STCT que el
  Sales Invoice resolvería, cuando la sucursal fiscal está correctamente mapeada al Centro de Costos.
- **Impacto cero en Sales Invoice**: `erpnext_proposals` no engancha Sales Invoice y no altera
  `facturacion_mexico`; su `before_validate` de Sales Invoice sigue idéntico.
- Si la configuración fiscal no está completa (p. ej. Cost Center sin Branch mapeada), la Quotation se
  guarda sin impuestos y sin error — el comportamiento es defensivo por diseño.
- Acoplamiento por import a funciones "privadas" (prefijo `_`) de `facturacion_mexico`: se cubre con
  tests que verifican que los símbolos importados provienen del módulo de `facturacion_mexico` y que el
  adapter no llama al helper bloqueante.

## Alternativas descartadas

- **Modificar `facturacion_mexico`** para generalizar su `before_validate` a Quotation o exponer un
  wrapper público: descartada — la app está en producción y su comportamiento de Sales Invoice debe
  permanecer completamente intacto.
- **Duplicar la lógica de resolución** en `erpnext_proposals`: descartada — duplicaría la convención de
  nombres de STCT y la clasificación de items, con riesgo de divergencia frente a `facturacion_mexico`.
- **Importar `_set_stct_by_branch`**: descartada por su comportamiento bloqueante (`frappe.throw`) y sus
  `msgprint`, inadecuados para una cotización comercial.
