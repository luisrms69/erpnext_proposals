# ADR-0017: Items requeridos y modelo económico aditivo de la propuesta

**Fecha:** 2026-09-01
**Status:** Propuesto — pendiente de aprobación; Fase 1 implementable, Fase 2 obligatoria de corto plazo
**Rama:** feat/required-items → version-16
**Relacionado:** supersede parcialmente [ADR-0002](0002-rentabilidad-estimada-propuesta.md); consume la relación
N:M de [ADR-0016](0016-relacion-nm-item-scope-item.md)

---

## 1. Contexto

`Quotation` es el documento base de la propuesta; `Quotation.items` son las líneas **vendidas**;
`Scope Item` es la actividad/esfuerzo reutilizable; la relación **N:M `Item ↔ Scope Item`** (ADR-0016)
materializa el alcance en `Quotation Scope Item` (snapshot), que congela al pasar Borrador → En Revisión y
alimenta Project/Tasks y la Rentabilidad Estimada.

Al modelar coordinación de proyecto (PMO) apareció una limitación: para **traer un conjunto de Scope Items**
se usaron Items agrupadores (p. ej. metodologías de PMO) y se agregaron a `Quotation.items`. Pero eso los
convierte en **líneas comerciales reales** (aparecen en `Quotation.items`, pueden salir en el PDF comercial,
pueden propagarse a Sales Order), cuando en varios casos representan **componentes necesarios para cumplir la
propuesta pero no vendidos como línea**: licencias internas, hardware, servicios de partner, subcontratación,
herramientas, o la propia coordinación PMO cuando no se cobra como línea.

Además, el reporte de Rentabilidad ya resuelve costo de item con fuentes nativas, pero (a) **anula** el costo
externo de un item que tiene Scope Items (`covered_by_scope`), lo que **rompe la reventa** (una licencia
vendida + comprada + con aprovisionamiento pierde su costo de compra); y (b) **no congela** el costo de item,
por lo que cambios futuros de pricing alteran la rentabilidad histórica. ADR-0002 dejó explícitamente
"compras/gastos fuera de alcance" y "sin campos adicionales de snapshot económico" — decisiones que esta
propuesta revisa.

## 2. Decisión

Mantener **`Item` nativo de ERPNext** como unidad central tanto para lo vendido como para lo requerido. La
diferencia **no** está en el maestro Item, sino en **dónde se usa dentro de la Quotation**:

- **`Quotation.items`** = Items **vendidos** (aportan ingreso; pueden aportar costo externo y Scope Items).
- **Nuevo child `Proposal Required Item`** (`Quotation.required_items`) = Items **necesarios pero no vendidos**
  (no ingreso; pueden aportar costo externo y Scope Items).

Ambos caminos usan **el mismo resolver N:M** `resolve_scope_items_for_item()` y materializan alcance en la
**misma** `Quotation Scope Item`. **No** se crean maestros ni sistemas paralelos.

El modelo económico pasa a ser **aditivo**: `costo_total = costo_externo + costo_laboral`, con las tres
dimensiones (ingreso / costo externo / esfuerzo) resolubles sobre la **misma** línea sin duplicarla.

## 3. Fase 1 (implementable en este ciclo)

**Nuevo child DocType `Proposal Required Item`:**
- `item` (Link → Item, reqd)
- `qty` (Float, default 1)
- `uom` (Link → UOM, default `Item.stock_uom`) — **necesaria**: el pricing nativo de compra es por UOM.
- Snapshot de costo (ocultos/read-only): `frozen_cost_rate` (Currency), `frozen_cost_source` (Data),
  `cost_locked` (Check).

**Custom Field en Quotation:** `required_items` (Table → Proposal Required Item).

**Generación de alcance:** `_generate_scope_items` / `add_missing_scope_items_from_items` /
`resync_scope_from_catalog` pasan a iterar **`items ∪ required_items`** por el mismo resolver. Se conserva la
clave de procedencia/dedup **`(item_code, scope_item)`** (ver §5) y todo el comportamiento actual: nuevos
Items (vendidos o requeridos) agregan Scope Items faltantes; no se duplica la pareja; borrar una fila y
guardar **no** la repone; resync no repone eliminadas; freeze/snapshot y Project/Tasks intactos.

**Costeo externo (§6 + §9):** `external_cost = 0` si `Item.is_purchase_item == 0`; si `== 1`, resolver por
pricing **nativo** ERPNext; sumar aditivo al costo laboral. **Quitar** el zeroing de `covered_by_scope`.

**Freeze (§7):** en Borrador el costo externo es vivo; al pasar a En Revisión se congela por línea
(`frozen_cost_rate/frozen_cost_source/cost_locked`) en `Quotation Item` (custom fields nativos) y en
`Proposal Required Item`. El reporte, en documentos submitted, **lee exclusivamente el snapshot**.

**Valuación (§ Consecuencias):** el reporte distingue **Costo de compra / Costo de esfuerzo / Costo total** y
suma Required Items comprables al costo externo.

## 4. Fase 2 — Recurrencia económica (obligatoria de corto plazo; NO se implementa en este ciclo)

Propuestas con ingresos/costos en distintos meses y recurrencias distintas (servicio administrado mensual,
licencias mensuales, partner desde el mes 3, implementación inicial concentrada, hardware único). Objetivo:
producir `Mes | Ingreso | Costo externo | Costo laboral | Margen | Margen %` **conservando** el total.

Modelo conceptual aprobado:
- **Reglas de recurrencia nullable/aditivas** en las líneas (Quotation Item y Required Item): intervalo,
  offset de inicio, número de periodos.
- **Calendario económico**: en Borrador = **proyección viva**; en En Revisión = **calendario mensual
  explícito congelado por periodo** (filas explícitas, no "tarifa × N").
- **Distribución del costo laboral** leyendo la temporalidad **ya existente** de Scope Items
  (`planned_start_offset_days`, `planned_duration_days`, `is_milestone`, `moment`, `phase`), sin duplicar la
  planificación de Project/Tasks: el calendario es **lectura/proyección**, no un segundo almacén.

**Handoff (futuro, no ahora):** vendidos recurrentes → Subscription (party Customer) / SO; requeridos
recurrentes → Subscription (`party_type=Supplier` → Purchase Invoice, verificado en v16) / compras. Precios
variables por periodo **no** mapean 1:1 a un Subscription Plan (tarifa fija); el calendario de propuesta es
**forecast**, el handoff es paso separado.

## 5. Modelo de Scope Items

`Quotation Item.item` **y** `Proposal Required Item.item` → **mismo** `resolve_scope_items_for_item()` →
**misma** `Quotation Scope Item`. Sin segundo sistema de alcance. Scope Items siguen siendo la **fuente única
del esfuerzo** y la base posterior de Project/Tasks.

**Clave de procedencia/dedup: `(item_code, scope_item)`** (no dedup global por `scope_item`). Motivo: dos
Items distintos pueden requerir **legítimamente** el mismo Scope Item como **esfuerzos separados** (p. ej. dos
licencias, cada una con su aprovisionamiento). Cuando el esfuerzo es genuinamente **compartido** (una sola
coordinación PMO entre componentes), el usuario **elimina** la fila sobrante (comportamiento ya soportado: no
reaparece). Un dedup global eliminaría esfuerzo legítimo y se rechaza.

**Bug latente conocido:** `create_project_from_quotation` mapea dependencias por `task_by_scope`
(`scope_item → Task`) con **last-wins** cuando el mismo `scope_item` aparece desde múltiples Items. Afecta
solo la **resolución de dependencias entre Tasks**, no la creación de Tasks ni el costeo. Se documenta y se
traslada a un **Issue separado**; **no** bloquea Fase 1 (no rediseñar Project/Tasks aquí).

## 6. Modelo de costos (aditivo)

```
external_cost(item) = 0                        si Item.is_purchase_item == 0
external_cost(item) = pricing_nativo(item)     si Item.is_purchase_item == 1
labor_cost(item)    = Σ (Quotation Scope Item del item: horas × costing_rate)
total_cost(item)    = external_cost + labor_cost      # independientes y aditivos
```

Casos:
- **A. Servicio propio** — ingreso; `is_purchase_item=0` → externo 0; laboral desde Scope Items.
- **B. Licencia de reventa** — ingreso; compra → externo; Scope Items opcionales → laboral; suma ambos.
- **C. Hardware de reventa** — ingreso; compra → externo; instalación → laboral; suma ambos.
- **D. Required Item comprado** — sin ingreso; compra → externo; Scope Items opcionales → laboral; suma ambos.

El gate por `is_purchase_item` evita costos externos espurios en servicios propios sin recurrir a heurísticas
del tipo "si encuentra un costo, súmalo".

## 7. Freeze / snapshot

Snapshot mínimo por línea (vendida y requerida): `frozen_cost_rate`, `frozen_cost_source`, `cost_locked`.
Congelado en **moneda base** (convertir en el freeze; no se guarda moneda adicional salvo que el código lo
demuestre indispensable). Sin costo al congelar → `frozen_cost_rate = 0`, `frozen_cost_source = "sin_costo"`,
`cost_locked = 1`. Documentos submitted/congelados leen **exclusivamente** el snapshot (mismo patrón
`use_frozen` que la tarifa laboral). Cambios posteriores de Item Price / last_purchase / valuation / listas
**no** alteran la rentabilidad histórica.

## 8. Reventa

Una **sola** línea vendida soporta las tres dimensiones sin repetir el Item en Required Items: ingreso
(`qty × rate`), costo externo (`is_purchase_item` + pricing nativo) y costo laboral (sus Scope Items).
`Proposal Required Item` queda **exclusivamente** para componentes necesarios que **no** son línea vendida.

## 9. Pricing nativo ERPNext (reutilización, no reimplementación)

Se reutiliza **`erpnext.stock.get_item_details.get_item_price(pctx, item_code)`** (verificado en v16,
`get_item_details.py:1263`), que ya maneja nativamente **UOM**, **vigencia** (`valid_from/valid_upto` vs
`transaction_date`) y **supplier**. Contexto (`pctx`): `price_list` (**buying**), `uom` (línea),
`transaction_date` (fecha de la Quotation; **Fase 2** podrá pasar la fecha del periodo). La **buying price
list** se determina de forma determinista reutilizando configuración nativa (p. ej. `Buying Settings`).
Fallback tras el pricing nativo: `Item.last_purchase_rate` → `Item.valuation_rate` → sin costo. **Sin**
Supplier Quotation automática (se retomará solo con referencia explícita por oportunidad/línea en el futuro).

## 10. Alternativas descartadas

- **Flag "no vendido" en `Quotation Item`** → fluye a Sales Order y puede salir en el PDF comercial; mezcla
  semántica comercial. Rechazada.
- **BOM (Bill of Materials)** → semántica de manufactura, innecesariamente pesada. Rechazada.
- **`Cost Item` / `Scope Package` / `Proposal Package`** → maestros/catálogos paralelos innecesarios;
  el Item nativo + N:M ya cubre el caso. Rechazadas.
- **Dedup global por `scope_item`** → elimina esfuerzo legítimo cuando dos Items requieren la misma actividad
  como esfuerzos separados. Rechazada (se conserva `(item_code, scope_item)`).
- **Supplier Quotation más reciente automática** → toma la SQ más reciente del `item_code` globalmente y
  **contamina** oportunidades distintas. Rechazada para Fase 1.

## 11. Consecuencias

- La Rentabilidad Estimada evoluciona a: **Ingresos** (Quotation Items) − **Costos externos** (Quotation Items
  comprables/reventa + Required Items comprables) − **Costo laboral** (Quotation Scope Items) = **margen** y
  **margen %**, distinguiendo Costo de compra / Costo de esfuerzo / Costo total.
- Quitar el zeroing de `covered_by_scope` **cambia números** de rentabilidad para items-con-scope: es el
  comportamiento **correcto** (aditivo), y solo afecta propuestas **no congeladas**; las congeladas usan su
  snapshot.
- Se introduce `uom` en el modelo económico (necesaria para costear licencias/hardware y para el pricing
  nativo).
- Posible **doble conteo** de esfuerzo si dos Items comparten un Scope Item que en realidad es un solo
  esfuerzo → se mitiga con **borrado manual** (respetado). El bug de dependencias `task_by_scope` se traslada
  a Issue separado.

## 12. Compatibilidad / migración

- **Aditivo**: child nuevo vacío por default; custom fields nuevos. **Sin backfill, sin migración one-off.**
- Quotations existentes **sin** Required Items conservan su comportamiento; propuestas congeladas intactas.
- **N:M Item ↔ Scope Item (ADR-0016)**, `Quotation Scope Item`, freeze/snapshot, Project/Tasks, propuesta
  comercial, SOW, loader y **packs privados** siguen compatibles.
- **Loader/packs:** Fase 1 **no** requiere que el catálogo declare Required Items de una Quotation. El pack
  sigue declarando `Item`, `Scope Item` y la relación N:M; los Items agrupadores (p. ej. de metodología PMO)
  siguen siendo Items nativos con Scope Items asociados; el usuario los selecciona como Required Items cuando
  corresponda.

**ADR-0002 — supersede parcial.** Siguen **vigentes** de ADR-0002: cadena única de verdad, no crear módulo
paralelo, rentabilidad como reporte interno, `billing_rate` no se usa como costo. Este ADR **reemplaza**
específicamente: (a) "compras/gastos fuera de alcance"; (b) "ausencia absoluta de campos adicionales de
snapshot económico".

## 13. Restricciones de compatibilidad Fase 1 → Fase 2

1. Fase 1 **no** debe asumir que toda línea es pago/costo **único**.
2. Los campos de recurrencia futuros serán **aditivos/nullable** (línea sin recurrencia = one-shot).
3. El freeze económico evolucionará a **calendario explícito por periodo** (filas, no tarifa × N).
4. **No** introducir ahora campos que obliguen a rediseñar `Proposal Required Item` para recurrencia
   (nada de fechas/periodos/montos por periodo en Fase 1).
5. El pricing nativo debe poder recibir **`transaction_date` por periodo** en Fase 2 (ya soportado por
   `get_item_price`).

## 14. Decisiones diferidas

- Supplier Quotation como fuente explícita por oportunidad/línea (`cost_source_reference`).
- Recurrencia económica completa (Fase 2): reglas en línea + calendario congelado + distribución laboral.
- Handoff post-venta de recurrencia (Subscription Customer/Supplier, Material Request/RFQ/PO).
- Guardar moneda original + tipo de cambio por periodo (auditoría FX); FX por periodo.
- Fix del `task_by_scope` last-wins (Issue separado; no bloquea Fase 1).
- `supplier`/`warehouse`/`company`/`currency` almacenados en Required Item.
- Declaración de Required Items desde el catálogo/loader.
