# Items requeridos y costo de la propuesta

Una propuesta tiene dos tipos de Items, **ambos son Items nativos de ERPNext** — la diferencia es dónde se
usan en la Quotation:

| | Dónde | Ingreso | Costo externo | Scope Items (esfuerzo) |
|---|---|---|---|---|
| **Items vendidos** | `Items` (tabla nativa) | Sí | Sí, si es comprable | Sí |
| **Items requeridos** | `Items requeridos` (tabla) | **No** | Sí, si es comprable | Sí |

Los **Items requeridos** son componentes necesarios para **cumplir** la propuesta pero que **no se venden
como línea** al cliente: coordinación (PMO), licencias internas, hardware, servicios de partner,
subcontratación, herramientas. **No** aparecen en `Items`, **no** generan ingreso y **no** pasan como
línea vendida a Sales Order; sí pueden aportar costo y Scope Items.

## Cómo se usa (grupo Propuesta)

En la Quotation, en la pestaña **Propuesta**:

- **Items** — lo que vendes (ingreso).
- **Items requeridos** — tabla simple: **Item + Qty** (la UOM se toma del Item; editable). Sin botones nuevos.

Cada Item requerido que tenga Scope Items asociados **los carga igual que un Item vendido**, en la misma
tabla de alcance (`Scope Items`), usando el mismo resolver Item ↔ Scope Item
(ver [Scope Items reutilizables](scope-items-reutilizables.md)).

**Ejemplo:** vendes una *Bolsa de Horas*; agregas como **Item requerido** un item de *PMO* que arrastra sus
Scope Items de coordinación — sin convertir el PMO en una línea comercial. La Quotation mantiene **una sola**
línea vendida.

Reglas de alcance (iguales para vendidos y requeridos):
- al agregar un Item vendido o requerido **nuevo**, se incorporan sus Scope Items faltantes;
- no se duplica la misma pareja Item↔Scope Item;
- si eliminas una fila de alcance y guardas, **no reaparece**;
- *Agregar Scope Items desde Items* y *Sincronizar alcance* consideran ambas fuentes;
- dos Items distintos que apuntan al mismo Scope Item generan **dos filas** (dos esfuerzos); si es un solo
  esfuerzo compartido, elimina la fila sobrante manualmente.

## Precarga automática (opcional)

Para que la preventa capture sobre todo **Items vendidos** y no tenga que recordar todo lo requerido, el
sistema puede **precargar** automáticamente. La precarga se configura en **Proposal Settings**
(*Configuración de propuestas*) y solo la ven `System Manager` y `Proposals Manager`.

**La configuración es por Compañía.** Cada `Company` tiene su propia fila de Proposal Settings (como máximo
una): abres la lista y creas una por Compañía —Compañía A con sus reglas, Compañía B con reglas distintas,
Compañía C sin configuración—. Al elaborar una propuesta, el sistema usa **solo** la configuración de la
Compañía de esa Quotation; si esa Compañía no tiene configuración, no se precarga nada (no se hereda de
otra Compañía).

- **Reglas de Items requeridos** — mapeo *Item o Item Group vendido → Item requerido*. Al agregar un Item
  vendido nuevo, sus Items requeridos configurados se agregan solos a la tabla **Items requeridos**. Una
  regla específica de **Item** tiene prioridad sobre la de su **Item Group** (no se combinan).
- **Scope Item de abastecimiento** — un Scope Item por defecto que se agrega al alcance de **todo Item
  comprable** (vendido o requerido), para representar la tarea de comprar/aprovisionar. Se puede excluir un
  Item concreto marcando en el Item **«Omitir tarea de abastecimiento»** (`proposal_skip_procurement`).

La precarga es **solo un punto de partida**: una vez agregadas, las filas son de la propuesta. Puedes
borrarlas, agregar otras o hacer excepciones; **lo que borras no reaparece** al guardar. Sin Proposal
Settings para la Compañía de la propuesta, no hay precarga y todo se captura manualmente (comportamiento
base).

## Costo de la propuesta (valuación económica)

El reporte **Rentabilidad Estimada** (interno) suma de forma **aditiva**:

- **Ingresos** — Items vendidos.
- **Costo de compra** — costo externo de Items vendidos **comprables** + Items requeridos **comprables**.
- **Costo de esfuerzo** — Scope Items (horas × tarifa de perfil/actividad).
- **Margen** = Ingresos − Costo de compra − Costo de esfuerzo.

**Costo externo** (de compra): solo aplica si el Item tiene marcado **`Is Purchase Item`**. Se resuelve con
el **pricing nativo de ERPNext**, en este orden:
1. **Buying Item Price** vigente (de la lista de compra configurada en *Buying Settings*).
2. **Último precio de compra** (`last_purchase_rate`).
3. **Valuation Rate**.
4. sin costo (se avisa).

Un **servicio propio** (`Is Purchase Item` desmarcado) no arrastra costo externo: su costo es el esfuerzo
(Scope Items). Una **reventa** (licencia/hardware, comprable) suma **costo de compra + esfuerzo**. Estos
costos son **independientes**: tener Scope Items ya **no** anula el costo de compra del Item.

## Congelamiento

Mientras la Quotation está en **Borrador**, el costo de compra se calcula en vivo. Al pasar a **En
Revisión** se **congela** por línea (junto con el esfuerzo, las secciones y el Print Format). Después,
cambios de Item Price, listas de precios o `last_purchase_rate` **no** alteran la rentabilidad histórica de
esa propuesta.

> Nota de arquitectura: este modelo está definido en
> [ADR-0017](../adr/0017-required-items-modelo-economico-aditivo.md). La recurrencia económica (ingresos/
> costos por mes) es la evolución de corto plazo (Fase 2) y aún no está implementada.
