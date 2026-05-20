# ADR-0002: Rentabilidad Estimada de Propuesta

**Fecha:** 2026-05-19
**Status:** Cerrado — implementado y mergeado (PR #7, 2026-05-20)
**Rama:** feature/proposal-profitability → mergeado a version-16

---

## Contexto

Una vez que la propuesta existe (Quotation + Scope Items + Project), hay suficiente información en ERPNext para estimar la rentabilidad **antes** de ejecutar el trabajo. Esta estimación es para uso interno de Buzola — no aparece en el PDF comercial ni en ningún documento visible al cliente.

El objetivo es responder: *¿cuánto cuesta hacer lo que vendimos, y cuánto margen estimado tenemos?*

---

## Decisión arquitectónica — Cadena única de verdad

**No se recaptura nada.** El reporte lee de la misma cadena ya construida:

```
Quotation Items                → venta estimada
  ↓
Quotation Scope Items          → horas estimadas + tipo de actividad
  ↓
Activity Type.costing_rate     → costo estimado por hora
  ↓
Project Tasks (futuro)         → ejecución planificada
  ↓
Timesheets (futuro)            → costo real de ejecución
  ↓
Sales Invoice Items (futuro)   → ingreso real facturado
```

El usuario selecciona una `Quotation` y el reporte resuelve todo lo demás. Sin recaptura, sin campos adicionales, sin módulo paralelo.

---

## Separación de conceptos financieros

| Concepto | Fuente | MVP |
|---|---|---|
| **Venta neta estimada** | `Quotation.net_total` (antes de impuestos) | ✅ |
| **Impuestos** | `Quotation.total_taxes_and_charges` | ✅ (informativo) |
| **Total con impuestos** | `Quotation.grand_total` | ✅ (informativo) |
| **Costo estimado de ejecución** | `Quotation Scope Items.estimated_hours × Activity Type.costing_rate` | ✅ |
| **Ingreso real** | `Sales Invoice Items.amount` ligados al SO | Futuro |
| **Costo real de ejecución** | `Timesheet Detail.hours × Activity Type.costing_rate` por Task del Project | Futuro |
| **Gastos / compras** | Purchase, Expense Claims, Project Costing ERPNext | Fuera de alcance por ahora |

**`billing_rate` no se usa para rentabilidad.** Solo puede mostrarse como referencia informativa. La venta real viene de Quotation Items, no de billing_rate.

---

## Fuentes de datos (todas ERPNext nativas)

| Dato | Fuente | Campo |
|---|---|---|
| Venta neta (base rentabilidad) | `Quotation` | `net_total` |
| Impuestos (informativo) | `Quotation` | `total_taxes_and_charges` |
| Total con impuestos (informativo) | `Quotation` | `grand_total`, `currency` |
| Horas estimadas por tarea | `Quotation Scope Item` | `estimated_hours` |
| Tipo de actividad por tarea | `Quotation Scope Item` | `activity_type` |
| Costo estimado por hora | `Activity Type` | `costing_rate` |
| Tarifa de venta por hora (referencia) | `Activity Type` | `billing_rate` |
| Horas reales (futuro) | `Timesheet Detail` → `Task` → `Project` | `hours` |
| Ingreso real (futuro) | `Sales Invoice Item` | `amount` |

**No se toca:**
- `Item` nativo
- Ningún campo de precio/costo en DocTypes propios
- Ningún módulo financiero externo a ERPNext

---

## Cálculos

### Costo estimado

```
Para cada Quotation Scope Item:
  si activity_type tiene costing_rate:
    costo_row = estimated_hours × costing_rate
  si no:
    costo_row = 0  (advertencia: "sin tarifa")

Total costo estimado = Σ costo_row con tarifa
```

### Margen estimado

Base de rentabilidad: **`net_total`** (venta antes de impuestos). Los impuestos no son margen.

```
margen_estimado_$  = net_total − total_costo_estimado
margen_estimado_%  = margen_estimado_$ / net_total × 100
```

El reporte muestra las tres líneas:
```
Venta neta:             net_total
Impuestos:              total_taxes_and_charges   (informativo)
Total con impuestos:    grand_total               (informativo)
```

### Post mortem (futuro) — Estimado vs Real

```
horas_estimadas  = Σ Quotation Scope Items.estimated_hours
horas_reales     = Σ Timesheet Detail.hours (Tasks del Project de la Quotation)
delta_horas      = horas_reales − horas_estimadas

costo_estimado   = calculado arriba
costo_real       = Σ Timesheet Detail.hours × Activity Type.costing_rate

venta_estimada   = Quotation.net_total
ingreso_real     = Σ Sales Invoice Items.amount (SO origen de la Quotation)

margen_estimado  = venta_estimada − costo_estimado
margen_real      = ingreso_real − costo_real
```

---

## Limitación de moneda — IMPORTANTE

**MVP confiable solo cuando Quotation y costos están en la misma moneda base de la Company.**

Si `Activity Type.costing_rate` está denominado en MXN y la Quotation está en USD (u otra moneda), el margen calculado será incorrecto porque el reporte no convierte tipos de cambio. Debe mostrarse una advertencia visible cuando `Quotation.currency ≠ Company.default_currency`.

---

## Arquitectura del MVP

**Script Report** en Frappe — no botón. Razones:

- Permite filtrar y comparar múltiples Quotations
- Exportable a Excel nativo
- No modifica ningún flujo existente
- Más fácil de testear y auditar

El reporte recibe como filtro principal: `Quotation` (nombre). Opcionales: rango de fechas.

Si existe una `Sales Order` ligada a la Quotation (`proposal_project` → `Project.sales_order`), se muestra como referencia informativa pero **no es la fuente de datos principal en MVP**. La venta se lee siempre desde la Quotation.

### Estructura del reporte

```
Propuesta: [título]     Cliente: [nombre]    Folio: [QTN]    Moneda: [MXN]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ALCANCE ESTIMADO

Fase          Tarea                  Actividad     Horas   $/h Est.   Costo Est.
─────────────────────────────────────────────────────────────────────────────
Planeación    Kick Off               Consultoría    1h      $800       $800
Ejecución     Configuración API      Implementac.   8h      $1,200     $9,600
...           [sin tarifa]           —             4h      —          —  ⚠

              TOTAL horas: 47h      TOTAL costo estimado: $XX,XXX
              (N tareas sin tarifa — costo subestimado)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VENTA (Quotation Items)

Concepto                     Qty    Precio Unit.    Total
API para generación CFDI      1      $45,000        $45,000
...

              TOTAL venta: $XX,XXX

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RENTABILIDAD ESTIMADA

  Venta estimada:         $XX,XXX
  Costo estimado:         $XX,XXX   (basado en N/M tareas con tarifa)
  ─────────────────────────────────
  Margen estimado:        $XX,XXX   (XX%)

⚠ Moneda: MXN. Confiable solo si todos los costos están en MXN.
⚠ Costo estimado calculado parcialmente: N de M tareas sin Activity Type.costing_rate.
  El margen mostrado puede ser artificialmente alto.
```

---

## Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| `Activity Type.costing_rate` no configurado | Costo subestimado | Advertencia visible; mostrar cuántas tareas quedan sin tarifa |
| Scope Items sin `activity_type` | Sin costo calculable para esa tarea | Mostrar como "sin tarifa" |
| Moneda Quotation ≠ moneda costos | Margen incorrecto | Advertencia cuando `currency ≠ default_currency` |
| Costo real diverge del estimado | Margen estimado ≠ margen real | Diseñado para ser solo estimación; post mortem en etapa siguiente |

---

## Post mortem — diseño futuro

El ADR establece desde ahora que el diseño debe evolucionar a comparación Estimado vs Real:

| Métrica | Estimado (hoy) | Real (futuro) |
|---|---|---|
| Horas | `Σ estimated_hours` | `Σ Timesheet.hours` |
| Costo | `horas × costing_rate` | `Σ Timesheet.hours × costing_rate` |
| Venta | `Quotation.grand_total` | `Σ Sales Invoice.amount` |
| Margen | calculado | calculado |

Esto requiere que:
1. El Project esté vinculado a la Quotation (ya implementado: `proposal_project`)
2. Los Timesheets estén registrados con `activity_type` y `task`
3. Las Sales Invoices estén vinculadas al SO

---

## Decisiones confirmadas

1. **MVP = Script Report**, no botón todavía
2. **Filtro principal = Quotation** — SO solo como referencia informativa si existe
3. **Base de rentabilidad = `net_total`** (antes de impuestos) — `grand_total` solo informativo
4. **Mostrar costo por fila** y total — no solo total
5. **Sin `costing_rate`**: advertencia "Costo calculado parcialmente, margen puede ser artificialmente alto"
6. **`billing_rate` no se usa para rentabilidad** — solo referencia informativa opcional
7. **MVP confiable solo en moneda única** — advertir cuando `currency ≠ default_currency`

---

## Archivos a tocar

| Archivo | Acción |
|---|---|
| `erpnext_proposals/erpnext_proposals/report/profitability_estimate/` | Crear directorio |
| `profitability_estimate.json` | Metadata del reporte (Script Report, doctype: Quotation) |
| `profitability_estimate.py` | Lógica de cálculo |
| `hooks.py` | Ningún cambio — reportes se autodescubren |

Sin fixtures, sin Custom Fields, sin DocTypes nuevos.
