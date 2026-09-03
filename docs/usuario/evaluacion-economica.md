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
| Item CAPEX | CAPEX | Ingreso una vez (pago único). Su adquisición puede financiarse — ver «Financiamiento del CAPEX» |

El **costo de esfuerzo** (laboral) se reparte en el tiempo usando lo que ya tienen los Scope Items (inicio y
duración): una actividad de 60 días que empieza al inicio reparte su costo entre los meses que cubre; un hito
(o duración 0) carga su costo en un solo mes.

## Dónde revisar la evaluación

La evaluación económica se lee en el **PDF de Rentabilidad** de la propuesta — el único documento de lectura y
aprobación. Se obtiene con los botones que ya existen en la Quotation: **«Vista previa rentabilidad»** (abre el
PDF) y **«Descargar PDF rentabilidad»**; es el mismo documento que se adjunta a la propuesta al pasar a **En
Revisión**.

El reporte sigue una narrativa de lectura rápida (**vendemos → cuesta → financiamos → margen**):

1. **Resumen** — una frase que resume el caso + indicadores clave (ingreso, costos, costo financiero, margen
   operativo, margen final y %, plazo, horizonte).
2. **Composición económica** — **NRC**, **MRC** y **CAPEX** por componente (con cadencia, periodos y acumulado
   en MRC). Cada categoría aparece siempre; si está vacía se indica «Sin componentes …».
3. **Esfuerzo y PMO** — actividades agrupadas por **perfil** con horas, tarifa y costo (subtotales por perfil).
4. **Financiamiento CAPEX** — qué se financia, a qué costo y el margen antes/después (si no hay, se indica).
5. **Evolución económica** — `Mes 0…N` con ingreso/costos/costo financiero/margen final por periodo.
6. **Anexo** — amortización, composición por periodo y controles de reconciliación.

El calendario es **relativo** (`Mes 0` = inicio de la propuesta); las fechas reales llegan con el proyecto. Se
calcula al momento, no se guarda.

> La antigua pestaña «Evaluación Económica» dentro de la Quotation fue **retirada**: no se mantienen dos
> superficies para lo mismo. El documento de referencia es el PDF de Rentabilidad.

**Reporte analítico:** también queda el reporte **Evaluacion Economica** (menú Reportes) para análisis,
filtros y soporte.

## Financiamiento del CAPEX (nuestro costo, no una tasa al cliente)

Cuando la propuesta incluye **CAPEX** (una adquisición de infraestructura), a veces **nosotros** financiamos
esa compra. Ese financiamiento tiene un costo para nosotros —intereses y comisiones— que **reduce el margen**.
La Evaluación Económica lo calcula para que veas el margen **real** después de financiar.

Puntos clave:

- **Es NUESTRO costo de fondeo, no una tasa cobrada al cliente.** El precio de la propuesta no cambia; el CAPEX
  se le cobra al cliente igual que antes (una vez). Lo que se calcula aquí es cuánto nos cuesta a nosotros
  poner ese dinero por adelantado.
- **El capital prestado no es costo** (se recupera al cobrarlo). **Solo el interés y las comisiones** cuentan
  como costo financiero.
- La sección **solo aparece si la propuesta tiene CAPEX**. Se activa con **«¿Requiere financiamiento?»**.

Al activarlo verás cuatro datos (con valores por defecto que Finanzas mantiene por compañía):

| Campo | Qué es |
|---|---|
| **Monto financiado** | Cuánto financiamos. Por defecto = costo de adquisición del CAPEX. **No puede ser mayor** que ese costo (financiar de más es un error). |
| **Plazo de financiamiento (meses)** | En cuántos meses lo pagamos. Es independiente del plazo contractual. |
| **Costo anual (%)** | Lo que nos cuesta el dinero al año. |
| **Comisiones** | Cargo de apertura del financiador (se cuenta como costo en el Mes 0). |

En la pestaña, cuando hay financiamiento, se agregan:

- **Indicadores nuevos:** costo financiero, costo total con financiamiento, **margen tras financiar** y su %.
- **Memoria de financiamiento:** monto, % del CAPEX, plazo, costo anual, mensualidad, interés total, comisiones,
  y una **tabla de amortización** mes a mes (saldo, interés, capital, pago, saldo final).
- **Calendario:** dos columnas más (costo financiero y margen tras financiar por mes).

Si el financiamiento dura más que el plazo del contrato, el calendario se **extiende** para mostrar el costo
financiero de esos meses (con un aviso). Los ingresos recurrentes **no** se extienden: solo existen durante el
plazo contractual.

## Congelamiento

Mientras la propuesta está en **Borrador**, la evaluación es una proyección viva: si cambias la configuración
o los precios, se recalcula. Al pasar a **En Revisión** se **congela** el comportamiento efectivo (recurrente
o no, intervalo, conteo) junto con el plazo, los costos y los **parámetros de financiamiento** (monto, plazo,
tasa, comisiones). Después, cambiar la configuración de la compañía **no** altera la evaluación histórica de
esa propuesta.

## Qué no incluye todavía (fases siguientes)

Cobros/pagos (condiciones de pago y flujo de caja) y los indicadores VAN/TIR/payback y análisis de
sensibilidad llegan en fases posteriores, sobre este mismo calendario. El financiamiento del CAPEX (costo de
fondeo, amortización) ya está incluido; lo que falta es el **flujo de caja** y esos indicadores.

> Nota de arquitectura: modelo definido en
> [ADR-0018](../adr/0018-evaluacion-economica-por-periodos.md), continuación de
> [ADR-0017](../adr/0017-required-items-modelo-economico-aditivo.md).
