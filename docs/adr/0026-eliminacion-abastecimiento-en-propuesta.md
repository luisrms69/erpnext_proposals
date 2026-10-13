# ADR-0026: Eliminación del abastecimiento modelado en la propuesta (la compra se gestiona en Buying nativo)

**Fecha:** 2026-10-11
**Status:** Cerrado — vigente. Supersede los mecanismos de abastecimiento de [#55](0017-required-items-modelo-economico-aditivo.md) y #79.
**Rama:** feat/simplify-procurement → version-16
**Versión:** 0.36.0

---

## Contexto

Antes de esta decisión, ERPNext Proposals intentaba modelar la **compra** dentro de la propuesta con **tres
mecanismos superpuestos**, todos sobre `Proposal Settings` por Company:

1. **Paquete de Gestión de Compras** (`default_procurement_package_item`, issue #55). Si la propuesta tenía
   ≥1 Item comprable, se agregaba **una vez** un Item-paquete a `required_items` (con sus Scope Items) para
   representar el esfuerzo interno de gestionar compras. `_autoload_procurement_package` lo inyectaba en
   `validate` por diff.
2. **Scope de compra por obligación** (`default_purchase_scope_item`, issue #79). Cada **ocurrencia
   comprable aplicable** (Item vendido o requerido con `is_purchase_item=1`) generaba una **Task individual
   de compra** (`"Comprar — <item> × <qty>"`, 0 horas) vía un Quotation Scope Item de relleno.
3. **Bloqueo `sin_compra`** (`assert_program_prerequisites`). La transición a «Ganada» **fallaba** si una
   ocurrencia comprable no podía resolver su Scope de compra por falta de configuración.

Más un opt-out por Item: `Item.proposal_skip_procurement` («Omitir tarea de abastecimiento»).

Esto generaba fricción real y contradecía el propósito de la app. El caso testigo fue
**SAL-QTN-2026-00024** (licencias Microsoft): una propuesta de puro licenciamiento **no podía ganarse** sin
antes configurar un Scope de compra, cuando el modelo por Item ([ADR-0025](0025-generacion-project-tasks-por-item.md))
ya resuelve el seguimiento de un Item vendido sin alcance con su **Task operativa «Entregar»**. Además:

- **Duplicación conceptual.** Paquete (esfuerzo interno) + Task por obligación (seguimiento) + opt-out
  resolvían variantes del mismo problema con tres fuentes de verdad y configuración obligatoria.
- **Proceso de compras paralelo.** Las Tasks de compra **no** crean Material Request / Orden de Compra /
  factura: son seguimiento. ERPNext ya tiene **Buying nativo** para el ciclo real de compra. Modelarlo otra
  vez dentro de la propuesta era reconstruir, peor, lo que el ERP ya hace.
- **El costo externo no dependía de nada de esto.** La Rentabilidad Estimada ([ADR-0017](0017-required-items-modelo-economico-aditivo.md)/[ADR-0024](0024-costo-externo-multimoneda.md))
  calcula el costo de compra por el **pricing nativo** gateado por `is_purchase_item`, totalmente desacoplado
  de paquete/scope de compra.

## Decisión

**El abastecimiento deja de modelarse en la propuesta.** La compra se gestiona con el **flujo nativo de
Buying de ERPNext**, fuera de ERPNext Proposals. Se eliminan:

1. **`Proposal Settings.default_procurement_package_item`** y su autoload (`_autoload_procurement_package`,
   `_applicable_purchasables`).
2. **`Proposal Settings.default_purchase_scope_item`** y la generación de Scope/Task de compra por
   ocurrencia (`_is_applicable_purchasable_code`, `_append_fallback_scope`, la rama de compra de
   `_append_scope_rows_for_row` y de `_scope_task_subject`). **No** se conserva como override.
3. **El bloqueo `sin_compra`** (`assert_program_prerequisites`) de la transición a «Ganada».
4. **El Custom Field `Item.proposal_skip_procurement`** («Omitir tarea de abastecimiento»), ahora sin
   lógica que lo lea.
5. El Section Break `procurement_section` de `Proposal Settings`.

El alcance de cada ocurrencia pasa a ser **exclusivamente su Scope propio** (relación N:M,
`resolve_scope_items_for_item`). Un Item comprable vendido sin Scope propio se comporta **igual** que
cualquier Item vendido sin alcance: genera su **Task operativa «Entregar — <item>»** (ADR-0025), no una Task
de compra.

## Qué se conserva (sin cambios)

- **Task padre por Item vendido** y **Task operativa única** por ocurrencia sin alcance ejecutable (ADR-0025).
- **Scope Items reales** y los **paquetes de alcance** reutilizables (N:M, [ADR-0016](0016-relacion-nm-item-scope-item.md)):
  un paquete de alcance es un Item organizativo que agrupa actividades; **no** es el paquete de compras
  eliminado.
- **Required Items** y su autoload por `required_item_rules` ([ADR-0017](0017-required-items-modelo-economico-aditivo.md)).
- **Inferencia de Project Type** desde paquetes (`Item.proposal_project_type`, `_resolve_project_type`):
  independiente del abastecimiento, se mantiene.
- **Costo de compra** en la Rentabilidad Estimada: el costo externo nativo (gate `is_purchase_item` →
  Buying Item Price → `last_purchase_rate` → `valuation_rate`), con su congelamiento multimoneda
  (ADR-0017/0024), **intacto**.

## Consecuencias

- **SAL-QTN-2026-00024 puede ganarse sin configurar nada.** Una licencia Microsoft sin Scope Items genera su
  Task padre + una Task operativa «Entregar»; igual para cualquier Item sin alcance.
- **Sin configuración obligatoria de compras.** `Proposal Settings` ya no exige campos de abastecimiento.
- **Forward-only, sin migración de datos.** Instalación limpia (CI) y actualización de sites existentes son
  `bench migrate` estándar: no hay patch de datos, SQL ni limpieza manual.
  - En sites existentes, las columnas de los campos retirados en `Proposal Settings` quedan **huérfanas** (no
    se dropean) y el Custom Field `proposal_skip_procurement` **persiste** en la BD (los fixtures no borran
    registros retirados del JSON). Ambos son inertes: ninguna lógica los lee. Las propuestas/Proyectos
    históricos **no** se tocan.
- **La compra se ejecuta en Buying nativo.** Si un proyecto requiere seguimiento de compras, se usa Material
  Request / Purchase Order de ERPNext, no Tasks de la propuesta.

## Alternativas descartadas

- **Conservar el Scope de compra como override opcional.** Descartada: mantiene la segunda fuente de verdad y
  la configuración por Company para un problema que Buying nativo ya resuelve. La decisión del negocio fue
  **eliminar**, no degradar a opcional.
- **Conservar solo el paquete (esfuerzo interno) y quitar las Tasks por obligación.** Descartada: el esfuerzo
  interno de gestionar compras, si aplica, se modela como un Scope Item/paquete de alcance normal; no requiere
  un mecanismo dedicado de abastecimiento.

## Referencias

- Supersede: paquete de Gestión de Compras (#55) y Scope de compra por obligación + bloqueo `sin_compra` (#79).
- Relacionados: [ADR-0016](0016-relacion-nm-item-scope-item.md), [ADR-0017](0017-required-items-modelo-economico-aditivo.md),
  [ADR-0024](0024-costo-externo-multimoneda.md), [ADR-0025](0025-generacion-project-tasks-por-item.md).
