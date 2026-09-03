# Evaluación Económica (recurrencia y calendario)

La **Evaluación Económica** proyecta, mes a mes, los ingresos, costos y margen de una propuesta. **No pides
nada nuevo a la preventa**: se calcula sola a partir de lo que ya capturas (Items, cantidades, precios,
Required Items, Scope Items) y de una configuración administrativa por compañía.

## Qué captura la preventa

Lo de siempre. El **único** dato financiero nuevo visible en la Quotation es:

- **Plazo contractual (meses)** — cuántos meses dura el servicio recurrente. Se **precarga** desde la
  configuración de la compañía y puedes cambiarlo si esta propuesta lo requiere.

No marcas líneas como "recurrente" ni "único", ni capturas periodicidades: eso vive en la configuración.

## Cómo sabe el sistema qué es recurrente

En **Proposal Settings** (por compañía) se define el **comportamiento económico** por Item o Item Group. Cada
comportamiento se presenta con la terminología del cliente **NRC / MRC / CAPEX**:

- **NRC** (Non Recurring Charges) — pago único (licencia perpetua, implementación, hardware puntual). Es el
  valor por defecto si no hay regla.
- **MRC** (Monthly Recurring Charges) — se repite; se indica el **intervalo** (p. ej. mensual, anual) y **cada
  cuántos** (1 = cada intervalo, 3 = trimestral si el intervalo es mes).
- **CAPEX** — infraestructura/inversión; en Fase 2A se evalúa como pago único (el financiamiento —mensualidad,
  tasa— llega en Fase 2B).

**Precedencia** (igual que el resto de reglas): primero la regla específica del **Item**; si no hay, la de su
**Item Group**; si ninguna, **NRC**. La configuración es **por compañía**: una propuesta usa solo la de su
compañía.

El **importe siempre sale de la propuesta**: el precio de la línea (ingreso) y el costo de compra resuelto
(costo). La configuración **nunca** vuelve a pedir precios. Internamente el sistema usa
`one_time`/`recurring`/`infrastructure`; en pantalla y PDF siempre verás **NRC/MRC/CAPEX**.

## Qué significa cada caso

| Lo que capturas | Grupo | Resultado en la evaluación |
|---|---|---|
| Item vendido NRC | NRC | Ingreso una vez; costo de compra una vez si es comprable |
| Item vendido MRC | MRC | Ingreso cada periodo durante el plazo; si es comprable, también su costo cada periodo (misma línea, no se duplica) |
| Item requerido MRC | MRC | Solo costo, cada periodo (sin ingreso) |
| Item CAPEX | CAPEX | Se evalúa como pago único en 2A |

El **costo de esfuerzo** (laboral) se reparte en el tiempo usando lo que ya tienen los Scope Items (inicio y
duración): una actividad de 60 días que empieza al inicio reparte su costo entre los meses que cubre; un hito
(o duración 0) carga su costo en un solo mes.

## Dónde revisar la evaluación (desde la propia Quotation)

La evaluación es **parte de la Quotation**: abre la Cotización y ve a la pestaña **«Evaluación Económica»**. No
necesitas salir a Reportes ni volver a filtrar. Verás:

1. **Resumen económico** — ingreso contractual, costo externo, costo de esfuerzo, costo total, margen, margen %.
2. **NRC**, **MRC** y **CAPEX** — la composición por línea de cada grupo (con cadencia y acumulado contractual
   en MRC).
3. **Costo de esfuerzo (Scope Items)** — de dónde sale el costo laboral (item origen, fase, horas, tarifa,
   costo, inicio/duración, periodos).
4. **Calendario económico** — `Mes 0…N` con ingreso/costo externo/costo esfuerzo/costo total/margen, y una
   **trazabilidad** que explica cada cifra por sus componentes.

El calendario es **relativo** (`Mes 0` = inicio de la propuesta); las fechas reales llegan con el proyecto. Se
calcula al momento, no se guarda.

**PDF ejecutivo:** el reporte profesional se obtiene con los botones que ya existen en la Quotation —
**«Vista previa rentabilidad»** (abre el PDF) y **«Descargar PDF rentabilidad»**. Ese documento ahora es la
**Evaluación Económica** profesional: identificación, resumen (indicadores), NRC, MRC, CAPEX, fuentes de
costo, calendario con gráfico y trazabilidad. Es el mismo documento que se adjunta a la propuesta al pasar a
En Revisión.

**Reporte analítico:** también queda el reporte **Evaluacion Economica** (menú Reportes) para análisis,
filtros y soporte.

## Congelamiento

Mientras la propuesta está en **Borrador**, la evaluación es una proyección viva: si cambias la configuración
o los precios, se recalcula. Al pasar a **En Revisión** se **congela** el comportamiento efectivo (recurrente
o no, intervalo, conteo) junto con el plazo y los costos. Después, cambiar la configuración de la compañía
**no** altera la evaluación histórica de esa propuesta.

## Qué no incluye todavía (fases siguientes)

Cobros/pagos (condiciones de pago y flujo de caja), CAPEX financiado (mensualidad, tasa), y los indicadores
VAN/TIR/payback y análisis de sensibilidad llegan en fases posteriores, sobre este mismo calendario.

> Nota de arquitectura: modelo definido en
> [ADR-0018](../adr/0018-evaluacion-economica-por-periodos.md), continuación de
> [ADR-0017](../adr/0017-required-items-modelo-economico-aditivo.md).
