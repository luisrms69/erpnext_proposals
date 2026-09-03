# ADR-0018: Evaluación económica por periodos (comportamiento en catálogo, calendario relativo)

**Fecha:** 2026-09-02
**Status:** Aprobado — **Fase 2A y Fase 2B implementadas** en la rama `feat/required-items` (ver §7 bis
hardening 2A y §7 ter financiamiento 2B). Fase 2C (cobros/FX/escalamiento/VAN-TIR/sensibilidad) queda diferida
y **fuera de alcance** de este ADR.
**Rama:** feat/required-items → version-16
**Relacionado:** continúa [ADR-0017](0017-required-items-modelo-economico-aditivo.md) (modelo económico
aditivo + Items requeridos + precarga por Company); reutiliza el patrón de reglas por Company de Fase 1 bis.

---

## 1. Contexto

Fase 1 + 1 bis dejaron resuelto el **modelo económico aditivo** por línea: ingreso (Quotation Item), costo
externo gateado por `is_purchase_item` con pricing nativo, costo laboral desde Scope Items, freeze en
Borrador → En Revisión, Rentabilidad Estimada, Required Items + precarga y procurement configurables por
Company (`Proposal Settings`).

El cliente evalúa hoy sus propuestas en Excel dividiendo **NRC** (no recurrente), **MRC** (recurrente
mensual) y **CAPEX** (infraestructura que se compra y vende, eventualmente financiada), con descuentos,
plazos, mensualidades y algunas sensibilidades. Queremos conservar ese **modelo mental** sin copiar sus
limitaciones y, sobre todo, **sin trasladar clasificación económica a la preventa**.

**Principio rector (UX):** la complejidad vive en la **configuración administrativa del catálogo**, no en la
Quotation. Preventa sigue trabajando casi como hoy —Items, cantidades, precios/descuentos, Required Items,
Scope Items, condiciones comerciales— y la evaluación económica **nace** de esas capturas más la
configuración previa. Preventa **nunca** clasifica una línea como NRC/MRC/CAPEX ni captura cadencias ni
parámetros financieros en el flujo normal.

## 2. Decisión

1. **La naturaleza económica de cada línea se infiere**, no se captura: proviene del **comportamiento
   económico configurado por Item / Item Group** en `Proposal Settings` (por Company), más la **tabla de
   origen** (Quotation Item = ingreso; Proposal Required Item = costo).
2. **NRC = default implícito.** Una línea cuyo Item/Item Group no tiene comportamiento recurrente configurado
   se trata como **one-time**. No existe campo NRC.
3. **MRC = comportamiento `recurring` configurado.** La **cadencia** (intervalo + conteo) vive en la
   configuración, **no** en la Quotation. El **importe siempre sale de la propuesta** (rate de la línea para
   ingreso; costo externo resuelto de Fase 1 para costo). **Nunca** se re-captura precio en la configuración.
4. **CAPEX/infraestructura = comportamiento `infrastructure` configurado** por Item Group. La línea sigue
   siendo un Quotation Item normal (ingreso + costo si comprable + Scope + procurement de Fase 1 bis). Los
   parámetros financieros son **excepcionales** y quedan para Fase 2B (no se diseñan aquí).
5. **La evaluación es un calendario por periodos relativos `Mes 0…N`**, calculado **on-demand** como reporte
   sobre el snapshot congelado (mismo patrón que Rentabilidad Estimada). **Sin fecha absoluta** en Fase 2A.

## 3. Alcance de Fase 2A (contenido, mínimo)

**Configuración (`Proposal Settings`, por Company):**
- Nueva child de **comportamiento económico**: mapeo `source_type` (`Item` | `Item Group`) → `source` →
  `economic_behavior` (Select: `one_time` | `recurring` | `infrastructure`) y, **solo si `recurring`**,
  `interval` (Month/Year/…) + `interval_count` (Int). **Sin precio, sin moneda, sin qty.**
- `default_contract_term_months` (Int): plazo contractual por defecto de la Company.
- **Precedencia idéntica a Fase 1 bis:** regla específica de **Item** gana sobre regla de su **Item Group**;
  si ninguna, default implícito `one_time`. Reutiliza el mismo resolver de precedencia (hermana de
  `required_item_rules`).
- **Handoff por comportamiento (ver §6): diferido.** No se implementa ni se añade su configuración en Fase 2A
  (para no crear settings que aún no se usan). El procurement de Fase 1 bis sigue funcionando aparte.

**Quotation:**
- `proposal_contract_term_months` (Int): **precargado** desde `default_contract_term_months` y **editable**
  (override solo cuando un caso real lo exija). Es el **único** campo nuevo visible a preventa.
- **Ningún** flag NRC/MRC/CAPEX por línea. **Ninguna** cadencia capturada por preventa.

**Freeze (Borrador → En Revisión):** snapshot de los **parámetros efectivos** por línea que realmente se
usan: `economic_behavior`, `interval`, `interval_count` y el `contract_term_months` efectivo. **Nada más**
(en particular, **no** se congela moneda/FX en 2A — ver §7 y alternativas descartadas).

**Reporte nuevo `Evaluación Económica`** (on-demand): columnas por periodo `Mes 0…N` con **Ingreso, Costo
externo, Costo laboral, Costo total, Margen**, más **acumulados / resumen**. Sin persistencia adicional.

## 4. Comportamiento económico en el catálogo (no en la Quotation)

Una única child = un mapeo simple. La preventa **no** la toca durante la elaboración normal; la administra el
catálogo por Company. Ejemplos: `servicio puntual` → `one_time`; `licencia mensual` / `servicio administrado`
→ `recurring` (Month/1); `Item Group Infraestructura` → `infrastructure`.

**Dirección ingreso vs costo:** la da la tabla de origen (Quotation Item → MRC de ingreso; Proposal Required
Item → MRC de costo), coherente con Fase 1: el Required Item ya es la fuente de costo sin re-capturar precio.

## 5. Calendario relativo `Mes 0…N` (on-demand)

- **Eje temporal relativo**, sin fecha absoluta: `Mes 0` = inicio conceptual de la propuesta. La fecha real
  (proyecto/go-live) se resolverá **después**, cuando exista, sin rediseñar el motor.
- **Ingreso / costo externo one-time e `infrastructure`:** en `Mes 0`.
- **Ingreso / costo recurrente:** ocurre en `Mes 0, step, 2·step, …` dentro del `contract_term_months`, con
  importe tomado de la propuesta. El **paso** en meses = `interval_count × factor(interval)` con
  `factor(Month)=1`, `factor(Year)=12`; una cadencia **sub-mensual** (Week/Day) se redondea a **mensual
  (mínimo 1)** porque el calendario es mensual. Ej.: `Month/1`→mensual (12 cargos en 12 meses); `Month/3`→
  trimestral (`Mes 0,3,6,9`); `Year/1`→anual.
- **Plazo vacío (0/None):** no hay proyección recurrente por defecto; un `recurring` sin plazo **degenera a un
  único cargo en `Mes 0`** (comportamiento seguro).
- **Item vendido comprable y recurrente:** una **sola** línea vendida aporta ingreso **y** costo externo
  recurrentes (misma cadencia). **No** se duplica el Item en Required Items para representar su costo.
- **Costo laboral:** distribuido con la temporalidad **ya existente** de Quotation Scope Item, con regla
  simple, determinista y testeable:
  - periodo de inicio = `floor(planned_start_offset_days / 30)` (parseo defensivo: el campo es Data/string);
  - `is_milestone` o `planned_duration_days ≤ 0` → **costo puntual** en el periodo de inicio;
  - si no, reparto **proporcional** de `estimated_hours × costing_rate` por solapamiento de días en ventanas
    de 30 días (conserva el total). Sin curvas S, earned value ni capacity planning.
  - La tarifa laboral se toma congelada en submitted; en Borrador se resuelve en vivo (Cost Matrix), igual que
    la Rentabilidad Estimada.
- **Margen** = Ingreso − (Costo externo + Costo laboral), por periodo y acumulado; `margen %` sobre el ingreso
  contractual total.

### Interpretación económica por línea (sin captura de NRC/MRC/CAPEX)

| Caso | Origen + comportamiento | Ingreso | Costo externo | Costo laboral |
|---|---|---|---|---|
| A | Quotation Item + `one_time` | una vez (Mes 0) | una vez si `is_purchase_item` | por su timeline |
| B | Quotation Item + `recurring` | recurrente | recurrente si `is_purchase_item` (misma línea, sin duplicar) | por su timeline |
| C | Required Item + `one_time` | — | una vez si `is_purchase_item` | por su timeline |
| D | Required Item + `recurring` | — | recurrente si `is_purchase_item` | por su timeline |
| E | `infrastructure` (2A) | como one_time | como one_time | por su timeline |

## 6. Handoff operativo (diseño; **diferido**, no se implementa en 2A)

La evaluación prepara la ejecución, pero **no genera documentos operativos**. El diseño previsto (no
construido en 2A) reutiliza la **maquinaria de autoload de Scope Items** de Fase 1 bis: un comportamiento
podría tener asociado, **por configuración**, un Scope Item de handoff (p. ej. `recurring` → "Configurar
servicio recurrente"; `infrastructure` → Scope Item de infraestructura). Si no se configura, **no** se crea
ninguna Task; **nunca** Tasks genéricas obligatorias tipo "validar SO/PO". Estas Scope Items/Tasks servirían
de control humano (Ventas/Finanzas/Ops/PMO vía `phase`/`designation`) para decidir el documento real
(Subscription, Sales Order, Purchase Order, términos de pago) al ganar.

**Decisión 2A:** el handoff **no** se implementa ni se añade su configuración ahora, para no crear settings
sin uso. Se retomará en una fase posterior. El procurement de Fase 1 bis sigue operando de forma independiente
(ortogonal a `economic_behavior`).

## 6 bis. Presentación (UX): terminología del cliente e integración en la Quotation

La naturaleza económica se **infiere** (motor: `one_time`/`recurring`/`infrastructure`); la **presentación**
usa la terminología del cliente, **mapeada solo en la capa visible**:

| Motor (interno) | Presentación (cliente) |
|---|---|
| `one_time` | **NRC** (Non Recurring Charges) |
| `recurring` | **MRC** (Monthly Recurring Charges) |
| `infrastructure` | **CAPEX** |

No se usan en UI/PDF términos sustitutos ("Único", "One Time", "Recurrente", "Infraestructura"). El mapeo
vive en `group_label()` / `GROUP_LABELS`; la semántica del motor **no** cambia.

**Experiencia principal = dentro de la Quotation** (no obligar a ir a Reportes): nueva **pestaña
"Evaluación Económica"** en la Quotation (custom field HTML `proposal_economic_evaluation_html`) renderizada
por `public/js/quotation.js` en `refresh`, que consume el método **whitelisted**
`utils.economic_calendar.get_economic_evaluation` (modelo ya calculado; el JS **no** duplica lógica
financiera). Sin botones nuevos. El **Script Report `Evaluacion Economica`** se conserva para análisis /
filtros / soporte, pero deja de ser la vía principal.

**Modelo de presentación** (`get_economic_evaluation`, mismo motor/matemática, salida enriquecida): resumen;
composición por **NRC / MRC / CAPEX** por línea (item, cantidad, ingreso, costo externo, costo de esfuerzo
atribuible, margen; para MRC: cadencia, plazo, ingreso/costo por periodo y **acumulado contractual**); tabla
de **esfuerzo** (Scope Items: item origen, fase, horas, tarifa, costo, inicio/duración, periodos);
**calendario** `Mes 0…N`; y **trazabilidad** por componente en cada periodo (cada cifra se explica por sus
partes). CAPEX en 2A muestra solo ingreso/costo/margen base y declara que el tratamiento financiero llega en
Fase 2B.

**Reporte ejecutivo = sustitución del Print Format `Rentabilidad Estimada`** (Jinja): el diseño profesional
de la Evaluación Económica **reemplaza el HTML** del Print Format que ya usaban «Vista previa rentabilidad» /
«Descargar PDF rentabilidad» / el adjunto oficial. **No se crea un Print Format aparte**: se reutiliza el
mismo PF y mecanismo (mismo botón, mismo `/printview`, mismo `render_proposal_pdf`, misma protección de
documento oficial). Consume el **mismo** modelo vía jinja method `get_economic_evaluation` (registrado en
`hooks.jinja.methods`); **la lógica NO vive en Jinja** (deja de usar `get_profitability_data`). Estructura:
identificación, resumen (KPI cards), NRC, MRC, CAPEX, fuentes de costo (externo + esfuerzo), calendario con
**gráfico de barras en CSS** + tabla, y trazabilidad por segmentos (`Mes 0`, `Mes 1`, `Meses 2-11`). Sin
VAN/TIR/payback/sensibilidad/mensualidad CAPEX (Fase 2B/2C).

**Robustez de render (multi-motor):** el diseño es **agnóstico del renderer** — colores en hex literal (no
`var()` CSS, que QtWebKit no soporta), sin gradientes ni JS de gráficos (barras en CSS puro). Funciona igual
por **wkhtmltopdf** (legacy) y por **Gotenberg/Chromium** (ADR-0015). El motor decide el renderer por el
`proposal_renderer_profile` del PF, sin tocar la lógica económica.

**Único campo de captura nuevo visible:** `Plazo contractual (meses)`, ubicado alto en la pestaña Propuesta
(tras el título, antes de las tablas). Se mantiene la regla: preventa **no** clasifica NRC/MRC/CAPEX ni
captura cadencias por línea; NRC/MRC/CAPEX es **solo presentación** inferida de la configuración.

## 6 ter. Relación con Rentabilidad Estimada (decisión)

Decisión: **`Evaluación Económica` sustituye el diseño del Print Format `Rentabilidad Estimada`.** El PF
`Rentabilidad Estimada` conserva su **nombre y todo su cableado** (botón «Vista previa rentabilidad»,
«Descargar PDF rentabilidad», `attach_proposal_pdfs`, protección de documento oficial ADR-0012), pero su
**HTML** pasa a ser el reporte profesional de Evaluación Económica, que consume `get_economic_evaluation` (ya
no `get_profitability_data`). Así hay **una sola** experiencia ejecutiva, sin crear un Print Format aparte ni
botones/flujos nuevos, y **sin romper** el pipeline oficial (sigue generando/adjuntando su PDF).

El **Script Report `Profitability Estimate`** (que usa `get_profitability_data`) **se conserva** para análisis
tabular; también el **Script Report `Evaluacion Economica`** (calendario) y la pestaña de la Quotation. La
consolidación evita **dos** experiencias ejecutivas idénticas.

## 7. Motor por periodos (preparado, sin sobre-ingeniería)

El reporte se construye **iterando por periodo** con el importe resuelto por una función `f(periodo)` —hoy
constante—. Esto deja la puerta abierta a **escalamiento de precio, inflación de costo, FX por periodo y
tasas por periodo** (Fase 2C) **sin** agregar hoy snapshots que todavía no se usan. **Decisión explícita:**
en 2A **no** se congela moneda/FX por línea "por si acaso"; Fase 1 ya congela los importes económicos
necesarios y el motor por periodos es suficiente para incorporar FX cuando exista el requerimiento real.

## 7 bis. Hardening (base confiable para 2B/2C)

Antes de construir financiamiento (2B) e indicadores (2C), el motor 2A se endurece para ser correcto,
determinista, reconciliable y auditable:

- **Fuente única de cálculo.** `get_economic_evaluation` es la **única** estructura canónica; `get_economic_calendar` es una **proyección** de ella. Script Report, pestaña (JS), Print Format/PDF **consumen** esa estructura y **no** reimplementan ningún total. La distribución temporal del esfuerzo vive en **una** función (`_distribute_over_months`), usada por el detalle de esfuerzo, el calendario y la trazabilidad.
- **Invariantes (`_assert_reconciled`, se ejecuta en cada evaluación).** Reconcilian: ingreso/costo externo por grupo = total; costo total = externo+esfuerzo; margen = ingreso−costo; el calendario suma a los totales (ingreso/externo/esfuerzo/costo/margen); y por periodo, la suma de componentes = total del periodo. Si algo **no** cuadra → `EconomicEvaluationError` (nunca se presentan números inconsistentes en silencio).
- **Determinismo.** Mismos inputs → **estructura completa idéntica** (grupos, componentes, periodos, asignaciones, trazabilidad, resumen), no solo totales. Orden estable (child tables por `idx`, grupos NRC/MRC/CAPEX fijos, periodos `range`). Sin timestamps dentro del resultado.
- **Draft vivo vs freeze histórico.** En Borrador se reconstruye desde Quotation/Items/Required/Scope/Settings/pricing vivos. En **submitted** se usa el **snapshot** por línea (behavior/interval/count congelados; costo externo y tarifa laboral congelados de Fase 1). Cambios posteriores en Proposal Settings, comportamiento/cadencia, `default_contract_term_months`, Item Group, Item Price, Scope Item master o tarifas **no** alteran la evaluación histórica.
- **Periodos individuales.** El motor calcula **cada** `Mes 0…N` por separado (nunca asume que un rango es igual). La **presentación** puede **compactar** periodos **consecutivos idénticos** (`Mes 0`, `Mes 1`, `Meses 2-5`, `Mes 6`, `Meses 7-11`) vía `_collapse_periods` (solo presentación; no toca el cálculo; rompe el grupo si cambia cualquier flujo/componente).
- **Cadencia recurrente inválida = ERROR, nunca fallback.** Para una línea con comportamiento efectivo `recurring` (MRC), un `interval` no soportado (fuera de `Month/Year/Week/Day`, o vacío) o un `interval_count ≤ 0` **falla** con `EconomicEvaluationError` (mensaje que identifica el componente y la compañía). **No** se degrada silenciosamente a mensual: una configuración inválida podría reconciliar pero ser económicamente falsa. No se corrige la configuración automáticamente.
- **MRC requiere plazo contractual válido.** Si existe **al menos** un componente efectivo MRC y `proposal_contract_term_months` está vacío / es 0 / inválido → **error** explícito. **No** se infiere plazo ni se usa un default oculto durante el cálculo. Propuestas con **solo NRC y/o CAPEX** pueden evaluarse **sin** plazo (válido). El plazo debe quedar resuelto en la propia Quotation.
- **Plazo contractual ≠ horizonte económico.** `term_months` (plazo) controla la **recurrencia** (MRC). `economic_horizon_months` (derivado, no persistido) es el horizonte real necesario para mostrar **todos** los flujos: normalmente `= term`, pero se **extiende** si un Scope Item ejecuta después del plazo (p. ej. contrato 12 meses, esfuerzo hasta Mes 13 → horizonte 14). Extender el horizonte **NO** extiende los ingresos MRC (solo existen durante el plazo); los meses adicionales muestran **solo** los costos presentes (margen negativo si aplica). El costo **nunca** se descarta y se emite `warnings: labor_beyond_term` (claro: plazo vs horizonte); también se advierte de esfuerzo **no atribuible** a una línea. No se modifica el plazo guardado en la Quotation.
- **Memoria de cálculo recreable (pestaña Quotation).** Es la memoria/auditoría (no el reporte ejecutivo). El **esfuerzo** se identifica con datos **humanos**: **actividad** (título), **perfil** (`designation`, el mismo que usa `get_designation_cost`), **horas**, **tarifa** (con fuente), **costo**, inicio/duración, periodos. El **costo externo** trae origen (Quotation Item / Required Item), qty, costo unitario, **fuente congelada** (`buying_item_price`/`last_purchase_rate`/`valuation_rate`/`no_purchase`/`sin_costo`) y grupo NRC/MRC/CAPEX. Los IDs técnicos (Scope Item, item_code, fase) quedan como detalle secundario.
- **Resultado vs memoria: nada derivado se persiste.** Ingreso, margen, `Mes 0…N`, etc. **no** son Custom Fields — se calculan **on-demand**. Solo se persisten: configuración (Proposal Settings), captura (`proposal_contract_term_months`) y snapshots de freeze (behavior/interval/count por línea).
- **Económico (devengado) ≠ flujo de caja.** El calendario 2A es **económico** (reconocimiento de ingreso/costo por periodo), **no** flujo de caja (timing de cobros/pagos). Los cobros/pagos (Payment Terms) llegan en 2C; **VPN/TIR/payback se construirán sobre el flujo de caja**, no sobre el margen devengado. El calendario ya queda como **serie ordenada `periodo → flujo(s)`** suficiente para derivar después el cash flow y los indicadores.
- **CAPEX preparado para 2B.** `infrastructure` conserva identificación completa (línea, item, ingreso, costo de adquisición, grupo CAPEX) para que 2B añada financiamiento (monto financiado, plazo, tasa, PMT, propio vs tercero) **sin** cambiar la estructura del calendario.
- **Estética del Print Format: pendiente.** El diseño visual del reporte ejecutivo **no** alcanza aún las referencias; queda explícitamente para un pase posterior. El hardening prioriza certeza del cálculo.

## 7 ter. Fase 2B — Costo de financiamiento del CAPEX (implementada)

Fase 2B añade **una sola cosa** sobre 2A: el **costo de que NOSOTROS financiemos la adquisición del CAPEX**.
Es una capa **aditiva** que no toca ninguna cifra ni invariante de 2A.

- **Separación tajante precio-cliente vs costo-nuestro.** El financiamiento modelado es **nuestro costo de
  fondeo** (interés + comisiones del financiador). **No** es una tasa cobrada al cliente ni altera el precio de
  la propuesta. El precio al cliente sigue siendo el de las líneas (el CAPEX se cobra como ingreso una vez, en
  `Mes 0`, sin cambios respecto a 2A).
- **El principal no es costo.** Se financia un monto (`financed_amount`) y se paga en cuotas; el **principal se
  recupera** y por tanto **no** es costo. Solo el **interés + las comisiones** constituyen `financial_cost`.
- **Modelo aditivo (2A intacto).** Se conservan `total_cost` (externo + esfuerzo) y `margin` de 2A. Se añaden:
  `financial_cost`, `total_cost_with_financing = total_cost + financial_cost`,
  `margin_after_financing = margin − financial_cost` y su `%`. Los KPI y el margen de 2A **no** cambian.
- **Base financiable = costo de adquisición del CAPEX.** `financed_amount` por defecto = **costo externo del
  grupo CAPEX** (adquisición). El usuario puede financiar **parcialmente** (menos), pero **`financed_amount`
  mayor que el costo de adquisición del CAPEX es ERROR** (no se financia más de lo que cuesta adquirirlo).
- **Amortización PMT (vencido, mensual).** Cuota fija `payment = P·r / (1 − (1+r)^−n)` con `r =` tasa anual/12
  (si `r = 0` → `P/n` lineal). Por cuota: saldo inicial, interés (`saldo·r`), capital (`pago − interés`), pago,
  saldo final; la **última cuota amortiza el capital restante** para cerrar el saldo exactamente en 0. Redondeo
  a 2 decimales. Las **comisiones** entran como costo financiero en `Mes 0`; el **interés** de cada cuota entra
  en su periodo.
- **Horizonte se extiende, MRC NO.** Si el financiamiento dura más que el plazo contractual, el
  `economic_horizon_months` se **extiende** para mostrar el costo financiero de todos los meses; los **ingresos
  MRC no se extienden** (solo existen durante el plazo). Se emite `warnings: financing_extends_horizon`.
- **Fail-closed (nunca números falsos).** Con financiamiento activo: `financed_amount ≤ 0`, `> CAPEX`, plazo
  `≤ 0`, tasa `< 0` o comisiones `< 0` → `EconomicEvaluationError`. Activar financiamiento **sin** CAPEX en la
  propuesta también es error. La configuración inválida se detiene, no se degrada.
- **Invariantes 2B (en `_assert_reconciled`, además de las de 2A).** `total_cost + financial_cost =
  total_cost_with_financing`; `margin − financial_cost = margin_after_financing`; el calendario suma a esos
  totales; y sobre la amortización: `Σ capital = financed_amount`, `Σ pago = financed_amount + Σ interés`,
  `saldo final de la última cuota = 0`, `financial_cost_total = Σ interés + comisiones`.
- **Defaults de Company = SOLO precarga; la Quotation es autoritativa.** `Proposal Settings` añade
  `default_financing_term_months` y `default_financing_cost_rate` (mantenidos por Finanzas). Se **precargan**
  al **activar** el financiamiento (transición 0→1, `_default_financing`) y **nada más**. Después, los valores
  guardados en la Quotation mandan: el motor (`_effective_financing`) los lee **tal cual**, sin volver a
  consultar la Company. En particular, una **tasa 0% explícita es válida** y **no** se sustituye por la de la
  Company — **no hay fallback silencioso** de 0% a la tasa de la Company (evita sobrestimar el costo financiero).
- **Freeze financiero por inmutabilidad.** Los campos de financiamiento son `allow_on_submit=0`: al pasar a
  **En Revisión** (submit) quedan fijos en el documento, y como el motor lee solo el documento, la evaluación
  histórica es estable por construcción. Cambiar `Proposal Settings` después **no** la altera. No se
  materializa nada desde defaults en el freeze (eso sobrescribiría un 0% explícito).
- **UX de revelación progresiva (sin ruido).** La sección de financiamiento en la Quotation **solo aparece si la
  propuesta contiene CAPEX**. Al activarla, `financed_amount` se precarga con el costo de adquisición del CAPEX.
  Las alertas se muestran **por excepción** (MRC sin plazo, financiado > CAPEX, horizonte extendido, esfuerzo
  fuera de plazo, errores financieros). La pestaña muestra la **memoria de financiamiento** (monto, %, plazo,
  costo anual, mensualidad, interés total, comisiones + tabla de amortización mes a mes). El Print Format añade,
  **solo si hay financiamiento**, el KPI de costo financiero / margen tras financiar y una línea de resumen.
- **NO en 2B (queda a 2C).** No hay flujo de caja, VPN, TIR ni payback: el calendario 2B sigue siendo
  **económico (devengado)**, no cash flow. Financiar con **capital propio vs. tercero** (costo de oportunidad
  distinto) tampoco se distingue aún: 2B modela un único costo de fondeo por tasa.

## 8. Explícitamente fuera de Fase 2A

Diferidos a 2B/2C, sobre un calendario que ya funciona: **Payment Terms / cash flow** (cobros/pagos), **CAPEX
financiero** (inversión, plazo, tasa, mensualidad, financiado por nosotros/tercero), **VAN/NPV, TIR/IRR,
payback**, **FX** y **escalamiento/sensibilidad**.

## 9. Alternativas descartadas

- **Flags NRC/MRC/CAPEX por línea en la Quotation** → traslada clasificación a preventa; mala UX. Rechazada.
- **Subscription Plan como configuración de preventa** → re-declara `item`+precio+moneda+`cost_center` por
  plan (verificado en v16); el admin mantendría un plan por Item×cadencia y **duplicaría el precio** que ya
  vive en la línea, contra el principio de no re-captura. Rechazada como configuración; queda como posible
  **destino del handoff** al ganar (Subscription real: `party_type=Customer`→Sales Invoice /
  `party_type=Supplier`→Purchase Invoice, según `subscription.py`).
- **Cadencia (interval/count) por línea capturada por preventa** → duplica lo que el catálogo ya sabe.
  Rechazada; vive en la configuración.
- **Plazo por línea** → innecesario para el caso típico. Rechazado en 2A; default por Company + override de
  cabecera. Override por línea solo si un caso real lo exige (puerta abierta, no implementado).
- **Fecha absoluta / usar `transaction_date` como inicio de proyecto** → en 2A basta el eje relativo
  `Mes 0…N`. Rechazada la fecha absoluta ahora.
- **Congelar moneda + FX por línea "para 2C"** → snapshot no usado todavía. Rechazado hasta que 2C lo exija.
- **Tasks de handoff genéricas y obligatorias** → llenarían Projects de tareas que no aplican. Rechazadas; el
  handoff es **configurable** por comportamiento (§6).
- **DocType de calendario económico persistido** → los inputs quedan congelados en En Revisión, así que el
  grid es determinista y reproducible; persistirlo duplica estado. Rechazado en 2A (se calcula on-demand; se
  reconsideraría solo si se necesita firmar/exportar el grid como evidencia inmutable independiente).

## 10. Compatibilidad con Fase 1 / 1 bis

- La child de comportamiento económico es **hermana** de `required_item_rules`: misma Company, misma
  precedencia Item → Item Group → default. Sin fricción estructural.
- **Ortogonalidad:** `infrastructure` **no** reemplaza el gate `is_purchase_item` del procurement de Fase 1
  bis; son dimensiones independientes (comportamiento = naturaleza en el tiempo; procurement = tarea de
  compra). Un Item de infraestructura comprable sigue recibiendo su procurement scope como hoy.
- **Required Item recurrente = MRC de costo**, coherente con Fase 1 (Required Item = fuente de costo sin
  re-capturar precio).
- El reporte lee `economic_behavior` **efectivo por línea**; hoy proviene solo de la configuración, pero la
  interfaz permite un override por línea en el futuro sin rediseño.

## 11. Restricciones de compatibilidad 2A → 2B/2C

1. El motor del reporte debe ser **iterativo por periodo** (`f(periodo)`), aunque hoy `f` sea constante.
2. El eje es **relativo** (`Mes 0…N`); la fecha absoluta se inyecta después sin rediseñar.
3. El freeze de 2A congela **solo** comportamiento/intervalo/plazo efectivos; 2B/2C **añadirán** snapshots
   (financieros, FX) de forma aditiva/nullable, nunca rediseñando los de 2A.
4. La naturaleza se resuelve como **behavior efectivo por línea** para admitir override futuro sin migración.

## 12. Consecuencias

- Preventa **no** captura nada nuevo salvo un plazo **precargado y editable**. La evaluación sale de la
  propuesta.
- Se añade **una** child de configuración + **dos** campos (`default_contract_term_months` en Settings;
  `proposal_contract_term_months` en Quotation) + snapshot de parámetros efectivos + un **reporte**. Nada más.
- El calendario relativo por periodos es la base sobre la que se montarán cobros/pagos, CAPEX financiero y
  los indicadores (2B/2C) sin re-capturas.

## 13. Campos nuevos inevitables vs. los que NO se crean

**Inevitables (2A) — creados exactamente estos:**
- DocType child **`Proposal Economic Behavior Rule`** (`source_type`, `source` Dynamic Link, `economic_behavior`,
  `interval`, `interval_count`).
- En `Proposal Settings`: `economic_behavior_rules` (Table) + `default_contract_term_months` (Int).
- Custom field `Quotation.proposal_contract_term_months` (Int) — único campo visible a preventa.
- Snapshot de freeze por línea: custom fields en Quotation Item (`proposal_economic_behavior`,
  `proposal_billing_interval`, `proposal_billing_interval_count`) y campos en `Proposal Required Item`
  (`economic_behavior`, `billing_interval`, `billing_interval_count`), todos read-only.
- Motor `utils/economic_calendar.py` + Script Report **`Evaluacion Economica`** (no persiste calendario).

**Inevitables (2B) — creados exactamente estos:**
- En `Proposal Settings`: `default_financing_term_months` (Int) + `default_financing_cost_rate` (Percent).
- Custom fields en Quotation: `proposal_financing_enabled` (Check), `proposal_financed_amount` (Currency),
  `proposal_financing_term_months` (Int), `proposal_financing_annual_cost_rate` (Percent),
  `proposal_financing_fees_amount` (Currency), más el Section Break `proposal_financing_section`.
- Amortización + `financial_cost` como **cálculo on-demand** en `utils/economic_calendar.py` (no se persiste
  ningún importe financiero; los inputs se congelan en el freeze de En Revisión).

**NO se crean (duplicación / mala UX):** flags NRC/MRC/CAPEX por línea; Link a Subscription Plan por línea;
cadencia por línea; plazo por línea; cualquier re-captura de precio/moneda en la configuración; parámetros
financieros por línea; DocType de calendario persistido; snapshot de FX/moneda en 2A; configuración de handoff.

## 14. Etapas futuras (fuera de este ADR, para contexto)

- **Fase 2A** (este ADR): comportamiento en catálogo + plazo default + calendario relativo Mes 0…N (ingreso /
  costo externo / costo laboral / margen), on-demand, con freeze mínimo.
- **Fase 2B** (implementada, §7 ter): costo de financiar el CAPEX (nuestro fondeo) — amortización PMT, capa
  aditiva `financial_cost` / `total_cost_with_financing` / `margin_after_financing`.
- **Fase 2C:** cobros/pagos (Payment Terms), FX, escalamiento, VAN/TIR/payback, sensibilidad.
