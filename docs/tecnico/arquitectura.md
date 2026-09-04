# Arquitectura técnica — ERPNext Proposals

> Estado actual implementado. No incluye historia ni planes futuros.
> Última actualización: 2026-07-17

---

## Resumen

App Frappe sobre ERPNext que extiende `Quotation` con un flujo de aprobación interna,
generación de PDFs de propuesta comercial, catálogo de alcances y creación de proyectos
de ejecución. No reemplaza el flujo nativo de cotización — lo amplía con una capa narrativa
y de gestión.

---

## Módulos principales

| Módulo | Responsabilidad | Archivos clave | Estado |
|---|---|---|---|
| Workflow de aprobación | Validaciones y trazabilidad en transiciones de estado | `utils/workflow_validations.py` | Activo |
| Lifecycle de Quotation | Hooks de inserción, validación, submit y post-submit | `utils/quotation.py` | Activo |
| Versionado de propuestas | Crear nueva versión desde propuesta Rechazada | `utils/proposal_versioning.py` | Activo |
| Creación de proyecto | Crear Proyecto + Tasks desde Quotation Ganada | `utils/project.py` | Activo |
| Matriz de costos | Rebuild periódico de costos por Designation + Activity Type | `utils/cost_matrix.py` | Activo |
| Permisos | Guard de roles para endpoints críticos | `utils/permissions.py` | Activo |
| Print Formats | PDF comercial (default genérico), Rentabilidad Estimada (privado) y **SOW** (Statement of Work, opcional por plantilla); helpers Jinja | `print_format/`, `utils/printing.py` | Activo |
| Resolución de Print Format | Comercial: cadena override→template→default y congelamiento del efectivo (ADR-0005). **SOW:** `resolve_sow_print_format` desde `Proposal Template.sow_print_format` (otra representación del mismo contenido; mismo renderer). **Portada separada** (`separate_cover_page`) generalizada a cualquier documento oficial designado por la plantilla (comercial o SOW), sin nombres hardcodeados | `utils/print_format.py` | Activo |
| Loader de catálogos | Carga genérica e idempotente por ruta externa: Proposal Phases, Sections, Items (+ campos editoriales), Scope Items (incluye la relación N:M `"erpnext_items": [...]` — lista de Item codes; clave ausente = no toca, presente = sincroniza, vacía = limpia; valida duplicados y reporta Items inexistentes en `pending`), Proposal Templates, Print Formats y **Payment Terms / Payment Terms Templates** (ADR-0006) | `catalog_data/catalog_loader.py` | Activo |
| Reporte de rentabilidad | Fuente de datos compartida entre UI y Print Format. Modelo **aditivo** (ADR-0017): ingresos (Items vendidos) − costo externo de compra (Items vendidos/requeridos **comprables**) − costo de esfuerzo (Scope Items). Costo externo vía pricing **nativo** (`utils/item_cost.resolve_external_cost`: gate `is_purchase_item` → `get_item_price` → `last_purchase_rate` → `valuation_rate`), congelado al pasar a En Revisión (`proposal_frozen_cost_*` en Quotation Item y `frozen_cost_*` en Required Item) | `report/profitability_estimate/`, `utils/item_cost.py` | Activo |
| Evaluación Económica (Fase 2A) | Calendario económico por periodos relativos `Mes 0…N` (ingreso/costo externo/costo laboral/margen) calculado **on-demand** (no persiste). Naturaleza inferida del **comportamiento económico** configurado por Item/Item Group en `Proposal Settings` (ADR-0018): `one_time`/`recurring`/`infrastructure`, precedencia Item > Item Group > `one_time`. Recurrencia según `interval`×`interval_count` durante `proposal_contract_term_months`; costo laboral distribuido por la temporalidad de Quotation Scope Item (`floor(offset/30)` + reparto proporcional; milestone/duración 0 = puntual). Importes **desde la propuesta** (precio de línea / costo externo), sin re-captura. Motor **iterativo por periodo** (`_line_amount_for_period`) preparado para FX/escalamiento (Fase 2C) sin snapshots hoy. Freeze de behavior/interval/count por línea en En Revisión (`_freeze_economic_behavior`); en submitted usa **solo** el snapshot | `report/evaluacion_economica/`, `utils/economic_calendar.py` | Activo |
| Evaluación Económica — presentación (Fase 2A) | **Terminología del cliente**: `one_time`→**NRC**, `recurring`→**MRC**, `infrastructure`→**CAPEX** (mapeo solo en la capa visible, `group_label`/`GROUP_LABELS`; semántica del motor intacta). Modelo enriquecido `get_economic_evaluation` (**whitelisted** + jinja method en `hooks.jinja.methods`): resumen, composición por NRC/MRC/CAPEX por línea (MRC con cadencia + acumulado contractual), tabla de esfuerzo (Scope Items) y calendario con **trazabilidad** por componente. **Reporte ejecutivo = sustitución del PF `Rentabilidad Estimada`** (su HTML consume `get_economic_evaluation`, ya no `get_profitability_data`); reutiliza botón «Vista previa/Descargar rentabilidad», `render_proposal_pdf` y el adjunto oficial. **Sin PF nuevo.** Diseño **narrativo con paginación por contenido** (no una página por sección): Resumen (frase «vendemos→cuesta→financiamos→margen» + tira de KPIs) · **Composición = análisis de integración (APU) por componente vendido** (precio → insumos → esfuerzo detallado por actividad/perfil → costo integrado → margen; CAPEX con `unit × qty`; MRC por-mes vs contractual sin volver recurrente el esfuerzo puntual; **Required Items como costos requeridos** —atribuidos solo si hay vínculo de dato demostrable, si no van al bloque «no asignados»; **sin prorrateo**) · Esfuerzo/PMO (agrupado por perfil, subtotales — segunda perspectiva de los mismos datos) · Financiamiento (compacto, separado del costo operativo) · Evolución económica (calendario) · Anexo (amortización + trazabilidad por periodo + reconciliaciones). KPIs en **tablas** (no flexbox) y se oculta `.action-banner` del print-view → PDF limpio en wkhtmltopdf y Gotenberg (ADR-0015). **La pestaña «Evaluación Económica» fue retirada** (custom fields `proposal_economic_tab`/`proposal_economic_evaluation_html` eliminados; eran solo-UI): en `quotation.js` solo queda la UX de financiamiento (disclosure por CAPEX + precarga). El motor añade campos descriptivos por línea (`unit_price`/`impact_label`/`financeable`) y `effort_totals`, sin tocar totales. `get_economic_evaluation` es la **fuente única** (PF y Script Report la consumen). Script Report `Evaluacion Economica` + `Profitability Estimate` se conservan | `utils/economic_calendar.py` (`get_economic_evaluation`), `public/js/quotation.js`, `print_format/rentabilidad_estimada/` | Activo |
| Evaluación Económica — financiamiento CAPEX (Fase 2B) | **Costo de fondeo** de la adquisición del CAPEX (nuestro interés + comisiones, **no** una tasa al cliente; el **principal no es costo**). Capa **aditiva** sobre 2A: se conservan `total_cost`/`margin` y se añaden `financial_cost`, `total_cost_with_financing`, `margin_after_financing` (+ %). Amortización **PMT vencido mensual** (`_amortize`/`_effective_financing`): cuota fija (`P·r/(1−(1+r)⁻ⁿ)` o `P/n` si tasa 0), última cuota cierra saldo en 0, comisiones en `Mes 0`; **cuota `k` (1-based) → bucket `Mes k-1`** (0-based), con plazo `T` las cuotas `1..T` ocupan `Mes 0..T-1` (no es annuity-due; solo mapeo índice→bucket accrual). **Plazo ÚNICO = `proposal_contract_term_months`** (no hay plazo financiero independiente; ver ADR-0018 §15). `financed_amount` por defecto = costo externo del grupo CAPEX; **financiar > ese costo = error**. El financiamiento **NUNCA** extiende `economic_horizon_months` (queda contenido en `Mes 0..T-1`); el horizonte solo crece por **ejecución** (`warnings: labor_beyond_term`), nunca por financiamiento. **Fail-closed** (financiado ≤0/>CAPEX, **plazo contractual ≤0**, tasa <0, comisiones <0, financiamiento sin CAPEX → `EconomicEvaluationError`) + **invariantes 2B** en `_assert_reconciled`. **Default de Company = solo precarga** de la tasa (`_default_financing` al activar); el plazo lo aporta `proposal_contract_term_months`. Tras eso la Quotation es autoritativa — el motor lee la tasa del documento **sin fallback** a la Company (una **tasa 0% explícita es válida**). **Freeze por inmutabilidad** (campos financieros y `proposal_contract_term_months` con `allow_on_submit=0`): al submit quedan fijos y la evaluación histórica es estable. UX: sección **solo si hay CAPEX** (revelación progresiva en `quotation.js`), **plazo derivado read-only** («Plazo: N meses (plazo contractual)»), memoria de amortización en la pestaña, KPI financiero en el PF. | `utils/economic_calendar.py` (`_amortize`, `_effective_financing`), `utils/quotation.py` (`_default_financing`), `public/js/quotation.js`, `print_format/rentabilidad_estimada/`, `doctype/proposal_settings/` | Activo |
| Items requeridos | Items **no vendidos** necesarios para cumplir la propuesta (PMO, licencias internas, hardware, partner). Aportan costo externo y Scope Items por el mismo resolver N:M; **no** generan ingreso ni línea comercial (ADR-0017) | `doctype/proposal_required_item/`, `utils/quotation.py` | Activo |
| Override de Quotation | Bloquea `declare_enquiry_lost` en propuestas con workflow | `overrides/quotation_override.py` | Activo |
| Sales Order hooks | Propaga proyecto y cost center de Quotation a SO | `utils/sales_order.py` | Activo |

---

## Flujos principales

| Flujo | Entrada | Proceso | Salida | Docs relacionados |
|---|---|---|---|---|
| Creación de propuesta | Nueva Quotation con `proposal_group` | `before_insert` valida grupo único; `validate` genera scope items desde catálogo **solo para las líneas de `Item` nuevas** (las que no estaban en el guardado anterior, vía `get_doc_before_save`; en el primer guardado todas son nuevas). Un guardado normal posterior **no** repuebla el alcance: eliminar una fila y guardar **no** la repone, y editar precio/cantidad tampoco agrega filas. Las líneas fuente del alcance son los **Items vendidos (`items`) + los Items requeridos (`required_items`)**, tratados **por FILA ORIGEN** (`_source_rows`, no deduplicados por `item_code`). La **identidad de cada Quotation Scope Item es `(source_row, scope_item)`** (Tema 1): el `source_row` es el `name` estable de la child row origen (Frappe lo asigna antes de `validate`), y se persiste con `source_type` (`sold`/`required`). Así, **dos filas del mismo Item se materializan por separado** (`S1@fila-A1`, `S1@fila-A2`) y la **`qty` NO multiplica** (una fila comercial → una materialización de cada Scope Item asociado). El Scope Item se resuelve por la relación N:M (`resolve_scope_items_for_item`: child `erpnext_items` + legacy `erpnext_item`). Snapshots **legacy** sin `source_row` conservan la semántica anterior por `item_code` (sin backfill). **Precarga (ADR-0017 Fase 1 bis):** antes de generar el alcance, `_autoload_required_items` agrega —solo para Items vendidos **nuevos**— los Items requeridos configurados en el `Proposal Settings` **de `quotation.company`** (resolución estricta por Company, sin fallback global; regla de `Item` sobre `Item Group`), marcados `auto_generated=1`, sin duplicar ni reponer borrados y sin volver requerido un Item ya vendido; y `_applicable_scope_items` suma el Scope Item de **abastecimiento** (`default_procurement_scope_item` de esa Company) al alcance de todo Item **comprable** (vendido o requerido), salvo opt-out `Item.proposal_skip_procurement`, tanto en la generación como en el resync. También **congela el contenido editorial del `Item` en cada `Quotation Item`** (`_copy_item_proposal_fields`, solo líneas nuevas) y captura el `proposal_sections_snapshot` de las Proposal Sections **únicamente si está vacío** (un guardado normal posterior **no** lo regenera ni relee los maestros). También sincroniza `proposal_print_format` desde el Template (`sync_proposal_print_format_from_template`). **Plazo contractual (ADR-0018 Fase 2A):** al crear la Quotation, `_default_contract_term` precarga `proposal_contract_term_months` desde `default_contract_term_months` de la Company **solo si está vacío**; nunca reescribe un valor ya puesto por la preventa | Quotation en Borrador con scope, contenido de Item congelado y snapshot de secciones capturado | `utils/quotation.py` |
| Sincronizar alcance desde catálogo | Botón (solo Borrador) → `resync_scope_from_catalog` | **update + remove** (ya **no** agrega) sobre filas `auto_generated=1`: refresca campos controlados por catálogo y elimina las sin respaldo (Scope Item deshabilitado/borrado, Item quitado, **o cuya FILA ORIGEN `source_row` ya no existe** — Tema 1); preserva `include_in_proposal` y filas manuales (`auto_generated=0`). **No repone** filas eliminadas — reponer faltantes es exclusivamente la acción manual *Agregar Scope Items desde Items*. Devuelve `{updated, removed, total}`. También **regenera** el `proposal_sections_snapshot` desde los maestros vigentes — es la **única** vía de actualizar el snapshot, y solo mientras la propuesta siga en Borrador | Alcance y snapshot de secciones sincronizados con el catálogo vigente | `utils/quotation.py` |
| Agregar Scope Items desde Items | Botón (solo Borrador) → `add_missing_scope_items_from_items` | Acción **manual** explícita: revisa **todas las filas origen** de la Quotation y agrega únicamente las combinaciones `(source_row, scope_item)` faltantes (vía `resolve_scope_items_for_item`), sin duplicar ni eliminar nada — respeta la identidad por fila origen (Tema 1): repone solo la ocurrencia faltante, sin tocar otras filas del mismo Item. Es la única vía de reponer filas de alcance tras la captura inicial | Alcance con las combinaciones faltantes recuperadas | `utils/quotation.py` |
| Avance a En Revision | Workflow action "Enviar a Revision" | `validate_workflow`: valida campos, **conserva** el `proposal_sections_snapshot` ya capturado en Borrador (lo crea como fallback solo si viene un Borrador legacy sin snapshot), **congela las tarifas de costo** (idempotente por fila; también se aplica en el Submit de respaldo), genera y adjunta los **documentos oficiales** vía `attach_proposal_pdfs`: propuesta comercial + Rentabilidad Estimada + **SOW** (este último solo si la plantilla define `sow_print_format`). Los tres usan el mismo contenido congelado, el mismo renderer y quedan privados e inmutables (ver ADR-0012) | Quotation submitted (docstatus=1), snapshot de secciones inmutable, tarifas congeladas, PDFs (comercial, rentabilidad, SOW) adjuntos | `utils/workflow_validations.py` |
| Aprobación / Rechazo | Workflow action "Aprobar" o "Rechazar" | Registra `reviewed_by`, `reviewed_on`; si aprobada: registra `approved_by`, `approved_on` | Quotation en Aprobada o Rechazada con trazabilidad | `utils/workflow_validations.py` |
| Versionado | Quotation Rechazada + acción "Crear nueva versión" | Copia campos a nueva Quotation (incluye el `proposal_sections_snapshot` **literal**, el contenido congelado de cada `Quotation Item` y el `proposal_specific_scope` manual de cada línea, editable de nuevo en el Borrador nuevo); marca original como `superseded_by_proposal`; bloquea si hay proyecto activo en la versión anterior. **Regenera** el payment schedule válido para la nueva `transaction_date` (`_resolve_new_version_payment` / `_is_automatic_single_row`), no copia fechas viejas | Nueva Quotation en Borrador vinculada | `utils/proposal_versioning.py` |
| Marcar como Ganada | Workflow action "Marcar como Ganada" | Transición Enviada al Cliente → Ganada | Quotation en estado Ganada; habilita botón Crear Proyecto y Sales Order | `fixtures/workflow.json` |
| Crear proyecto | Botón "Crear/Ver Proyecto" (estado Ganada) | Crea Project + Tasks desde scope items; idempotente por `quotation.proposal_project` (reutiliza proyecto si ya existe). **`project_name`** = `proposal_title` (o `<cliente> — <grupo>`) **+ Proposal Group al final** (`_build_project_name`, Tema 2): no duplica si ya termina con el grupo; respeta el límite 140 truncando solo la base. **Fase (Tema 3):** cada Task padre de fase congela `color` de la Proposal Phase (nativo `Task.color`); su rango se **autocalcula** = envelope de sus Tasks hijas (`inicio = min(inicio de hijas fechadas)`, `fin = max(fin de hijas fechadas)`); una fase sin hijas fechadas no recibe fechas (no se inventan). El **`Project.expected_end_date`** = fin más tardío del plan (contiene todas las fases); `expected_start_date` se mantiene como el ancla del Project (fecha de la Cotización, base de los offsets). No hay segundo scheduler ni auto-expansión posterior (eso es responsabilidad del app `pmo`) | Proyecto ERPNext con Tasks vinculadas a scope items | `utils/project.py` |
| Propagación a Sales Order | Creación de SO desde Quotation Ganada | `validate` y `on_submit` propagan `proposal_project` y `proposal_cost_center` al SO | SO con proyecto y cost center heredados | `utils/sales_order.py` |
| Rebuild de costos | Scheduler diario o acción manual | Lee Activity Cost, Timesheets, Salary Assignments; upsert en Proposal Cost Matrix | Matriz actualizada; Log de cambios de tasa | `utils/cost_matrix.py` |

---

## DocTypes críticos

| DocType | Propósito | Relaciones | Notas |
|---|---|---|---|
| `Proposal Section` | Bloque de texto narrativo reutilizable | Referenciado por `Proposal Template Section` | Tiene flag `is_executive_summary` para resaltar en portada |
| `Proposal Template` | Agrupa secciones en orden para un tipo de proyecto | Tiene child table `Proposal Template Section` | Se cargan desde el **catálogo** (loader), **no** por `install.py` (ADR-0006). Campos de render: **`letter_head`** (Link → `Letter Head`, opcional; encabezado de marca de la familia, explícito por nombre) y **`separate_cover_page`** (Check, default `0`; PDF con portada separada + merge — ADR-0014) |
| `Proposal Template Section` | Fila de sección en un template | Link a `Proposal Section`; soporte para `custom_title` y `custom_content`; **`hide_title`** (Check, oculta el heading por Template); **`include_by_default`** (Check, default `1`; en `0` la sección es opcional por propuesta); **`page_break_before`** (Check, default `0`; `1` = la sección inicia página nueva; independiente de `is_executive_summary`) | Child table de `Proposal Template` |
| `Proposal Optional Section` | Fila del selector de secciones opcionales activadas en una Quotation | Child de `Quotation` (custom field `proposal_optional_sections`, Table MultiSelect → `Proposal Section`) | Solo activa filas del Template marcadas `include_by_default=0`; se congela vía `proposal_sections_snapshot` (ver ADR-0013) |
| `Scope Item` | Actividad del catálogo maestro | Relación **N:M con `Item`** vía child `erpnext_items` (`Scope Item ERPNext Item`); campo legacy `erpnext_item` (Link único) conservado solo por compatibilidad de lectura. `phase` **Link a `Proposal Phase`** | Sin precio; describe trabajo, perfil y horas estimadas. Un mismo Scope Item puede aplicar a varios Items y un Item puede tener varios Scope Items. El resolver central `resolve_scope_items_for_item` une child + legacy (dedup). Se administra desde el formulario Item (botón *Scope Items* → `get/set_scope_items_for_item`). El **contenido editorial** del servicio (metodología, resultado esperado, límite del alcance) vive en el **Item**, no aquí. Sin backfill ni patch: la migración es solo de lectura |
| `Scope Item ERPNext Item` | Fila de la relación N:M Scope Item → Item | Child de `Scope Item` (tabla `erpnext_items`); campo único `item` (Link → `Item`) | Representa la asociación vigente Item ↔ Scope Item que alimenta la generación de alcance |
| `Quotation Scope Item` | Copia congelada de un Scope Item dentro de una Quotation | Parent: `Quotation`; link a `Scope Item`, `Task` y `phase`→`Proposal Phase`; **origen: `source_type` (`sold`/`required`) + `source_row`** (name de la child row origen) | Child table; identidad **por fila origen** `(source_row, scope_item)` (Tema 1) — distingue ocurrencias del mismo Item repetido. `rate_locked` se fija en transición a En Revision. Flags: `include_in_proposal` (visible en PDF) y `is_internal_cost_task` (tarea interna: entra en costo/rentabilidad, se excluye del PDF comercial) |
| `Item` (extendido) | Contenido comercial del servicio | Custom fields editoriales y de metadata administrados por el catálogo | Editoriales: `proposal_content_section`, `proposal_methodology`, `proposal_expected_result`, `proposal_scope_limit` — descripción/metodología/resultado/límite del servicio. Metadata de servicio (Data, opcionales, genéricos, SSOT): `proposal_service_validity` (Vigencia del servicio), `proposal_min_unit` (Unidad mínima), `proposal_service_hours` (Horario de servicio) — consumidos por binding en las Sections |
| `Quotation Item` (extendido) | Copia **congelada** del contenido editorial del Item dentro de la Quotation | Child de `Quotation` | `proposal_methodology`, `proposal_expected_result`, `proposal_scope_limit` copiados del Item al generar el alcance; el PDF usa esta copia y **no** relee el Item maestro. Además `proposal_specific_scope` (Text Editor): **alcance contratado manual** por línea — editable en Borrador, **no** viene del Item/catálogo (ver [ADR-0010](../adr/0010-alcance-especifico-contratado-quotation-item.md)) |
| `Proposal Phase` | Catálogo de fases (`phase_code`, `phase_name`, `sequence`, **`color`** Color) | Referenciado por `phase` en Scope Item / Quotation Scope Item | El orden en propuesta/reportes/Tasks usa `sequence`; el display usa `phase_name`. `color` (Tema 3) se **congela** en la Task padre de fase al generar el Project (campo nativo `Task.color`); cambiarlo después no altera Projects ya creados. **La duración de fase NO se captura**: el rango de la fase se autocalcula como el envelope de sus Tasks hijas. Helpers en `utils/phase.py` (`phase_label`, `order_phases`, jinja methods) |
| `Proposal Cost Matrix` | Costos por (Designation, Activity Type) | Alimenta freeze de costos en scope items | Rebuildeado diariamente; `is_general_rate=1` para filas de promedio por designación |
| `Proposal Cost Matrix Log` | Historial de cambios de tasa | Parent: ninguno | Append-only; creado por `cost_matrix.py` en cada cambio de tasa |
| `Quotation` (extendido) | Documento central; extendido con ~30 custom fields | Tiene child `Quotation Scope Item`; link a `Project`; child `Proposal Required Item` (custom field `required_items`) | Custom fields en fixture; extended class via `QuotationProposalMixin` |
| `Proposal Required Item` | Item **necesario pero no vendido** (sin ingreso; aporta costo externo y Scope Items) | Child de `Quotation` (`required_items`); `item` (Link → Item), `qty`, `uom` | ADR-0017. Snapshot de costo congelado (`frozen_cost_rate`/`frozen_cost_source`/`cost_locked`). `auto_generated` (Check oculto, solo auditoría) = precargado por regla. Alimenta el mismo alcance que los Items vendidos vía `_source_item_codes` |
| `Proposal Settings` | Configuración por `Company` (ADR-0017/0018; **no** Single) | `company` (Link, reqd/único, autoname `field:company`); child `Proposal Required Item Rule` (`required_item_rules`); `default_procurement_scope_item` (Link → Scope Item); child `Proposal Economic Behavior Rule` (`economic_behavior_rules`); `default_contract_term_months` (Int) | Editable por `System Manager` y `Proposals Manager`. **Máximo uno por Company** (autoname + `_assert_unique_per_company`). Resolución **estricta** por `quotation.company`: sin settings → sin precarga/abastecimiento/comportamiento (todo `one_time`); **sin fallback global** |
| `Proposal Required Item Rule` | Regla de precarga *Item/Item Group vendido → Item requerido* | Child de `Proposal Settings`; `source_type` (`Item`\|`Item Group`), `source` (Dynamic Link), `required_item` (Link → Item) | La regla de `Item` tiene precedencia sobre la de su `Item Group` (`_configured_required_items`) |
| `Proposal Economic Behavior Rule` | Comportamiento económico por *Item / Item Group* (ADR-0018 Fase 2A) | Child de `Proposal Settings`; `source_type`, `source` (Dynamic Link), `economic_behavior` (`one_time`\|`recurring`\|`infrastructure`), `interval`, `interval_count` | Precedencia Item > Item Group > `one_time` (`_economic_behavior_for_item`). Solo clasifica: el importe sale de la propuesta, aquí **no** hay precio |

---

## Modelo de contenido y congelamiento

El contenido de la propuesta se **captura y congela** dentro de la Quotation en el momento de su
elaboración (Borrador). El PDF y las versiones posteriores **nunca releen** los maestros del catálogo:
usan siempre la copia congelada. Así, un cambio posterior en el catálogo no altera propuestas ya
enviadas ni PDFs históricos.

### Contenido editorial del servicio: `Item` → `Quotation Item` (congelado)

El contenido comercial de cada servicio (descripción, metodología, resultado esperado y límite del
alcance) vive en **custom fields del `Item`**, administrados por el catálogo:

| Campo (custom) | DocType | Uso |
|---|---|---|
| `proposal_content_section` | `Item` | Section Break (agrupa el contenido de propuesta en el Item) |
| `proposal_methodology` | `Item` | Metodología del servicio (Text Editor) |
| `proposal_expected_result` | `Item` | Resultado esperado (Text Editor) |
| `proposal_scope_limit` | `Item` | Límite del alcance / servicios no incluidos (Text Editor) |
| `proposal_service_validity` | `Item` | **Metadata de servicio** — Vigencia del servicio (Data) |
| `proposal_min_unit` | `Item` | **Metadata de servicio** — Unidad mínima (Data) |
| `proposal_service_hours` | `Item` | **Metadata de servicio** — Horario de servicio (Data) |
| `proposal_skip_procurement` | `Item` | **Opt-out** (Check) — si está marcado, un Item comprable NO recibe el Scope Item de abastecimiento automático (ADR-0017 Fase 1 bis) |
| `description`, `proposal_methodology`, `proposal_expected_result`, `proposal_scope_limit` | `Quotation Item` | **Copia congelada** del contenido del Item dentro de la Quotation |

Al generar el alcance de una Quotation, `_copy_item_proposal_fields(doc)` (en `utils/quotation.py`)
copia esos cuatro campos del `Item` a cada línea nativa `Quotation Item`
(constante `_FROZEN_ITEM_FIELDS`). Reglas:

- **Generación inicial (Borrador):** solo congela las líneas **nuevas** (Item recién incorporado). Un
  guardado normal de un Borrador **no** relee ni pisa líneas ya congeladas.
- **Resync explícito** (`force=True`, botón *Regenerar alcance*, solo en Borrador): refresca los cuatro
  valores en **todas** las líneas desde el Item maestro.
- El Print Format comercial (y el híbrido *Servicios no incluidos*) lee `Quotation Item`, **no** el
  Item maestro.

> Decisión relacionada: el contenido editorial vive en el `Item`, **no** en `Scope Item`
> (los Scope Items solo describen actividad, perfil y horas). Ver ADR-0007.

### Alcance específico contratado por línea: `proposal_specific_scope`

A diferencia del contenido editorial (genérico, del catálogo), el **alcance concreto de la
contratación** de cada servicio se captura a mano en `Quotation Item.proposal_specific_scope`
(Text Editor). Propiedades y ciclo de vida:

- **Editable en Borrador** (`hidden=0`, `read_only=0`, `allow_on_submit=0`, `print_hide=1`, `reqd=0`):
  se escribe en la fila expandida de cada servicio.
- **Fuera de los conjuntos gestionados:** no está en `_FROZEN_ITEM_FIELDS` (copia `Item → Quotation
  Item`) ni en `_CATALOG_CONTROLLED_FIELDS` (refresco del resync). Por eso **un guardado, un
  *Regenerar alcance* y un `_copy_item_proposal_fields(force=True)` lo conservan** sin tocarlo.
- **Congelado al someter** con los mecanismos existentes (sin freeze paralelo): `allow_on_submit=0`
  más el hook `on_quotation_before_update_after_submit`, que rechaza cualquier edición post-submit
  fuera de las transiciones de workflow.
- **Heredado al versionar:** `create_new_proposal_version` lo copia en `_copy_item(...)`; queda
  editable de nuevo en el Borrador de la nueva versión, sin alterar la anterior.
- **Independiente por línea:** el mismo `Item` repetido puede tener alcances distintos.
- **Impresión:** el Print Format que lo consume (pack privado) lo lee **solo** desde `Quotation Item`
  y **únicamente si tiene contenido**; nunca relee Item/catálogo/Scope Item. Ver
  [ADR-0010](../adr/0010-alcance-especifico-contratado-quotation-item.md).

### Snapshot inmutable de Proposal Sections

El cuerpo narrativo (Proposal Sections del Template) se congela en el campo
`Quotation.proposal_sections_snapshot` (Long Text, JSON). Funciones en `utils/quotation.py`:

- `_build_sections_snapshot(doc)` — arma la lista de entradas desde el Template resuelto.
- `_sync_sections_snapshot(doc, force=False)` — captura el snapshot **solo si está vacío** (generación
  inicial en Borrador). Con `force=True` (resync en Borrador) lo **regenera** desde los maestros
  vigentes. Un guardado normal **no** lo regenera ni relee maestros.

Cada **entrada** del snapshot tiene: `sequence`, `title`, `content` (Jinja crudo), `source_section`,
`is_executive_summary`, **`hide_title`** y `captured_on`.

**Ciclo de vida del snapshot:**

| Momento | Qué pasa con el snapshot |
|---|---|
| Creación en Borrador | Se captura **una vez** (si está vacío) desde el Template |
| Guardado normal en Borrador | **No** se toca (no se relee el Template) |
| Resync (*Regenerar alcance*, solo Borrador) | **Única** vía de actualizarlo: se regenera desde los maestros vigentes |
| Borrador → En Revision (freeze) | Se **conserva** el ya capturado; solo se crea como fallback si un Borrador legacy no lo tenía. A partir de aquí es **inmutable** |
| Nueva versión (versionado) | Se copia **literalmente** (mismo contenido/orden/`captured_on`); no se consultan maestros |

**Lectura fail-closed** — `utils/printing.py::get_sections_snapshot(doc)` (expuesto como método Jinja):
valida el JSON y cada entrada (helpers `_is_nonempty_str`, `_valid_snapshot_entry`). Si el snapshot
está ausente, vacío o es inválido, devuelve `valid=False` y el Print Format muestra **solo** una
advertencia de no entrega — **no** renderiza alcance, inversión ni firma. Los snapshots históricos sin
`hide_title` siguen siendo `valid=True` (campo **no** requerido; retrocompatibilidad).

### `hide_title` — heading opcional por Template

`hide_title` (Check, default `0`) vive en **`Proposal Template Section`** (no en `Proposal Section`):
la misma Section canónica puede mostrar su heading en un Template y ocultarlo en otro sin duplicarse.
Se **congela** en cada entrada del snapshot. En el Print Format (`render_section`): `hide_title = 1` →
no se renderiza el `block-title` (el body sí); `0` o ausente → se muestra el heading. Ver
`tecnico/print-formats.md`.

### Secciones opcionales por propuesta (`include_by_default` + selector)

Una Section del Template puede declararse **opcional** apagando **`include_by_default`** (Check en
`Proposal Template Section`, default `1`). Las filas opcionales **solo entran al snapshot** si esa
Quotation las activó en el custom field **`proposal_optional_sections`** (Table MultiSelect →
`Proposal Optional Section`, editable solo en Borrador). El resto de filas (`include_by_default = 1`,
el default histórico) mantiene el comportamiento previo: siempre entran.

- `_build_sections_snapshot` construye el conjunto de Sections activadas desde `proposal_optional_sections`
  y descarta cualquier fila opcional no seleccionada. Una selección que no corresponda a una fila
  opcional del Template asignado se **ignora** (no puede inyectar secciones ajenas).
- La activación es **per-Quotation**, sin duplicar el Template ni tocar el Print Format: la sección
  hereda su `sequence` de la fila del Template (p. ej. `~640` para una cláusula legal de cierre, antes
  del bloque de aceptación) y se **congela** en el snapshot como cualquier otra.
- Como el snapshot se captura una sola vez en Borrador (o se regenera con *resync*, solo Borrador),
  activar/desactivar la sección **después de congelar no tiene efecto**. Para reflejar un cambio del
  selector en un Borrador ya poblado se usa *Sincronizar alcance desde catálogo*.

Ver **ADR-0013**.

---

## Loader de catálogos

Todo el contenido comercial (genérico o por cliente) se carga con el **loader genérico e idempotente**
`catalog_data/catalog_loader.py`, **explícitamente por ruta externa** — nunca en `install` ni `migrate`
(ADR-0006). El kit del catálogo es un JSON + assets (HTML/CSS de Print Formats) que vive **fuera** del
repo (privado por cliente).

### Qué siembra (por clave del JSON)

| Clave JSON | DocType destino | Identidad | Función |
|---|---|---|---|
| `letter_heads` | `Letter Head` | `letter_head_name` | `_seed_letter_heads` |
| `phases` | `Proposal Phase` | `phase_code` | `_seed_phases` |
| `sections` | `Proposal Section` | `section_name` | `_seed_sections` |
| `items` | `Item` (+ campos editoriales y de metadata de servicio) | `item_code` | `_seed_items` |
| `scope_items` | `Scope Item` | `code` / nombre | `_seed_scope_items` |
| `payment_terms` | `Payment Term` | `payment_term_name` | `_seed_payment_terms` |
| `payment_terms_templates` | `Payment Terms Template` | `template_name` | `_seed_payment_terms_templates` |
| `templates` | `Proposal Template` (+ filas de sección) | `template_name` | `_seed_templates` |
| `print_formats` | `Print Format` (HTML/CSS desde archivos del kit) | `name` | `_seed_print_formats` |

### Garantías del loader

- **Idempotente:** identidad por nombre/código; una segunda corrida no duplica.
- **`update_content`:** sin él, un registro que difiere del catálogo se reporta como **conflicto** (no
  se escribe); con `update_content=True`, se **actualiza** el contenido gestionado. Solo administra los
  campos provistos por el catálogo (`_managed_fields` / `_diff_managed`).
- **`clear_fields` (vaciado explícito, opt-in):** un objeto del catálogo puede declarar
  `"clear_fields": ["<campo>", ...]` para que esos campos de un registro **existente** queden vacíos. La
  **ausencia** de un campo en el JSON **nunca** vacía nada (seguro para upgrades/catálogos parciales);
  solo se vacía lo declarado. Genérico para los tipos soportados (Templates, Sections, Scope Items, Items,
  Phases, Letter Heads), **idempotente** (si ya está vacío no hay cambio), respeta `update_content`/`dry_run`
  y **valida** el campo (existe, no obligatorio, no de sistema/estructura ni tabla hija). Resuelve el hueco
  de que `update_content` no podía anular un campo que **desaparece** del catálogo (`_seed_clear_fields`).
- **`dry_run`:** previsualiza (Creados / Sin cambios / Actualizados / Conflictos) sin escribir.
- **Nunca borra registros:** 0 `delete_doc` en el código (`clear_fields` solo vacía campos, no borra docs).
- **Print Formats protegidos:** `Propuesta Comercial` y `Rentabilidad Estimada` (assets del repo
  público) están en `PROTECTED_PRINT_FORMATS`; el loader los reporta como conflicto y **nunca** los
  escribe (ADR-0005/0006).
- **`capabilities()`:** declara la versión de capacidades del loader (`LOADER_CAPS_VERSION`); el
  instalador del kit la verifica para exigir que el código del app en el bench destino soporte lo que
  el catálogo usa. **v9** (8 → 9) agrega: la clave **`letter_heads`** en `capabilities()`, soporte de
  los campos nuevos del Template (`letter_head`, `separate_cover_page`) en crear/diff/update, y los 3
  campos de metadata de servicio del Item en `_seed_items`.
- **Letter Heads dedicados (`letter_heads`, capacidad v9):** siembra idempotente por `letter_head_name`;
  el loader **nunca** los marca `is_default = 1`. El catálogo es **dueño de `is_default = 0`**, para
  garantizar que la selección del Letter Head sea **explícita por nombre** (vía
  `Proposal Template.letter_head`) y **no** el default implícito del sitio.

Invocación:

```bash
bench --site <site> execute \
  erpnext_proposals.erpnext_proposals.catalog_data.catalog_loader.run \
  --kwargs "{'catalog_path': '/ruta/al/catalogo.json', 'update_content': True, 'dry_run': True}"
```

---

## Integraciones externas

| Integración | Uso | Punto de entrada | Notas |
|---|---|---|---|
| ERPNext `Project` | Proyecto de ejecución creado desde propuesta ganada | `utils/project.py` — `create_project_from_quotation()` | ERPNext nativo; no se usa Project de Frappe base |
| ERPNext `Task` | Una tarea por scope item incluido en propuesta | `utils/project.py` — loop de scope_rows | Linked a `Quotation Scope Item.project_task` |
| ERPNext `Sales Order` | Hereda proyecto y cost center de la propuesta | `utils/sales_order.py` — hooks de validate y on_submit | El SO se crea nativamente; el app solo propaga campos |
| ERPNext `Activity Type` | Costing rate de fallback en ausencia de Activity Cost | `utils/cost_matrix.py` — `get_designation_cost()` | Tercer nivel de fallback en jerarquía de costos |
| HRMS `Salary Structure Assignment` | Proxy salarial de costo por hora (base/160h) | `utils/cost_matrix.py` — `_fetch_salary_data()` | Última fuente en jerarquía; solo si HRMS instalado |
| `Employee` + `Activity Cost` | Fuente primaria de costos por designación | `utils/cost_matrix.py` — `_fetch_activity_cost_data()` | Primera fuente en jerarquía de costos |
| Frappe `File` | Almacenamiento de PDFs generados | `utils/quotation.py` — `attach_proposal_pdfs()` | Tres documentos oficiales **privados**: Propuesta Comercial, Rentabilidad Estimada y **SOW** (prefijo `SOW - `, solo si la plantilla define `sow_print_format`). `get_proposal_documents_status()` (whitelisted) comprueba su existencia real (por prefijo de nombre, por el hash de `save_file`) para que el botón `Propuesta` (JS) oculte la acción de **re-generar** cada documento oficial una vez adjunto, sin quitar el acceso a los ya generados. Cada PDF oficial se marca con el Custom Field **`File.is_proposal_official_document`** (read-only, solo lo fija `_attach_pdf`) y su **borrado queda protegido** por `doc_events[File].on_trash` (`utils/official_document_protection.py`): ni usuarios ordinarios ni System Manager pueden eliminarlo, solo `Administrator` y el propio flujo de regeneración (flag `INTERNAL_REPLACE_FLAG`); persiste tras cancelar; no afecta otros adjuntos ni la descarga. Ver **ADR-0012** |
| Frappe Realtime | Notificación al cliente JS cuando PDFs están listos | `utils/quotation.py` — `frappe.publish_realtime()` | Evento: `erpnext_proposals_pdfs_attached` |
| `facturacion_mexico` (impuestos) | Impuesto automático en Quotation reutilizando la resolución fiscal existente | `utils/quotation_tax.py` — `apply_fiscal_taxes` (hook `Quotation.before_validate`) | **Read-only sobre `facturacion_mexico`** (solo `import`); ver abajo y **ADR-0008** |
| ERPNext `Contact` | Resolución y persistencia del contacto dirigido de la Quotation | `utils/quotation_contact.py` — `set_proposal_contact` (hook `Quotation.before_insert`), `autocorrect_missing_contact` (hook `Quotation.validate`) | Reúso nativo `get_default_contact`/`get_contact_details`; ver abajo y **ADR-0009** |
| Frappe CRM `CRM Deal` (opcional) | Contacto del Deal como autoritativo al crear la Quotation | `utils/quotation_contact.py` — `_deal_primary_contact` | Lectura **desacoplada** (guardada por `frappe.db.exists`); sin dependencia del app `crm` |
| Gotenberg (opcional) | Motor HTML→PDF desacoplado y versionado para Print Formats operativos | `utils/gotenberg.py` (`GotenbergClient`) + `utils/renderer.py` (dispatch en `render_proposal_pdf`) | Se activa por formato con el Custom Field técnico **`Print Format.proposal_renderer_profile`** (oculto/read-only; `legacy`=wkhtmltopdf por defecto, `gotenberg-v1`=Gotenberg). Endpoint por config de entorno **`proposal_gotenberg_url`** (fail-closed; sin fallback silencioso). Ningún Print Format lo adopta aún. Ver **ADR-0015** |

### Materialización de dependencias en Tasks del Project

Al crear el Project (`utils/project.py`), las filas `Task Depends On` de las Tasks resultantes provienen
de **dos capas** — importante para conciliar el conteo, porque el total supera al número de
dependencias fuente:

1. **Dependencias de negocio (el app) — hija→hija:** `_resolve_native_dependencies` traduce los códigos
   de dependencia **congelados** en cada `Quotation Scope Item` a relaciones `depends_on` **hija→hija**,
   solo cuando **ambas** Tasks están contratadas (predecesor incluido), con dedup e idempotencia. La
   resolución es **por OCURRENCIA** (Tema 1): el predecesor se busca primero dentro de la **misma fila
   origen** (`(source_row, scope_code)`); si no hay materialización en esa ocurrencia pero el predecesor es
   **único** en toda la propuesta, se usa esa única; si tiene **varias** materializaciones y ninguna en la
   ocurrencia actual (cross-ocurrencia ambigua) **no** se elige arbitrariamente (se elimina el *last-wins*
   por `scope_code`) → se omite y se cuenta en `dependencies_ambiguous`. Así, con un Item repetido,
   `S1@A1→S2@A1` y `S1@A2→S2@A2`, nunca cruzado. Su número es el de las aristas fuente **entre los scope
   items contratados** (un subconjunto del total del catálogo).
2. **Enlace de grupo (ERPNext core) — grupo→hija:** cada Task de fase es `is_group=1` y cada Task hija
   se crea con `parent_task` = su fase. El `on_update` nativo de ERPNext (`Task.populate_depends_on`)
   agrega **cada hija** al `depends_on` de su Task de grupo, deduplicado. Resulta en **exactamente una**
   relación grupo→hija por Task hija (cada hija tiene un solo `parent_task`). El app **no** crea estas
   filas.

Por eso `total Task Depends On = (aristas fuente entre contratados) + (1 por cada Task hija)`. No hay
dependencias derivadas entre fases ni otras reglas automáticas del app; ambas capas son **idempotentes**
(re-crear el Project no las duplica).

**Ejemplo verificado (E2E, solo `ERPNEXT-BASE`):** 104 Tasks hijas en 16 fases; **135** relaciones
hija→hija (las 135 aristas fuente entre esos 104 scope items — de las 197 del catálogo completo, el
resto involucra líneas opcionales no contratadas) + **104** grupo→hija = **239** filas `Task Depends On`.

### Impuesto automático en Quotation (reúso read-only de `facturacion_mexico`)

El adapter `utils/quotation_tax.py` (`apply_fiscal_taxes`, hook `Quotation.before_validate`) fija
automáticamente el `Sales Taxes and Charges Template` (STCT) de la Quotation **reutilizando por
importación** los helpers de resolución de `facturacion_mexico` (`_get_customer_default_cc`,
`_get_branch_from_cost_center`, `_get_border_zone_status`, `_determinar_variante_stct`,
`_find_stct_by_variant`). La aplicación final usa el nativo de ERPNext `get_taxes_and_charges`.

- **`facturacion_mexico` NO se modifica** — la reutilización es solo por `import` de funciones puras de
  lectura; su flujo de Sales Invoice permanece intacto (`erpnext_proposals` no engancha Sales Invoice).
- Solo aplica cuando **`quotation_to == "Customer"`**.
- Usa **`proposal_cost_center`** (o el CC por defecto del Customer) y la configuración fiscal existente
  **Centro de Costos → Branch (Oficina Fiscal) → zona → variante → STCT**.
- **No-op suave**: si no resuelve la configuración fiscal (sin CC, sin Branch mapeada, sin zona o sin
  STCT), no hace nada y **no bloquea** el guardado.
- **Respeta la selección manual**: si `taxes_and_charges` ya tiene valor, no lo sobrescribe.
- **No** importa `_set_stct_by_branch` (bloqueante) y **no** aplica la validación SAT estricta del
  Sales Invoice (clave SAT por línea, CC obligatorio).

Ver **ADR-0008**.

### Contacto dirigido de la Quotation (Deal → Customer)

El módulo `utils/quotation_contact.py` resuelve y **persiste** el contacto con el que va dirigida la
propuesta, dentro del ciclo normal del documento (sin patches, backfills manuales ni escrituras
directas a BD). Dos enganches, misma resolución (Deal → Customer), distinta autoridad:

- **`before_insert` — `set_proposal_contact` (autoritativo):** si la Quotation nace de un `CRM Deal`
  con contacto válido, ese contacto **gana** sobre el prefill del CRM o el *fetch* nativo. Sin contacto
  del Deal, *fallback* al contacto por defecto del Customer (`get_default_contact`).
- **`validate` — `autocorrect_missing_contact` (solo-si-vacío):** aplica únicamente cuando
  `docstatus == 0`, `quotation_to == "Customer"` y `contact_person` está **vacío**. Rellena (Deal; si
  no, Customer) y **no sobrescribe** un contacto ya definido. Así un Draft antiguo sin contacto se
  corrige solo al guardarse; los documentos Submitted/frozen no se tocan.

- La lectura del Deal (`_deal_primary_contact`) está **desacoplada del app `crm`**: consulta por
  `frappe.db` y solo si el DocType `CRM Deal` existe. Prioridad: fila `is_primary = 1` → `CRM Deal.contact`
  → primera fila; el candidato se descarta si no existe como `Contact`.
- Los derivados (`contact_display`/`contact_email`/`contact_mobile`/…) se pueblan con el nativo
  `get_contact_details`. El **Print Format** sigue usando `doc.contact_display` sin lógica especial —
  con esto el PDF muestra la **persona** y no el nombre de la empresa.

Ver **ADR-0009**.

---

## Permisos y workflows

| Área | Roles | Regla crítica | Implementación |
|---|---|---|---|
| Crear propuesta (Quotation) | Proposals User, Proposals Manager | `proposal_group` es obligatorio al insertar | `utils/quotation.py:before_insert` |
| Avanzar workflow (Borrador → En Revision) | Proposals User, Proposals Manager | Requiere template, cost center y total > 0 | `utils/workflow_validations.py:_validate_blocking` |
| Aprobar / Rechazar | Proposals Manager | Proposals User no puede aprobar ni rechazar | Fixture `workflow.json` — transición restringida por rol |
| Marcar como Ganada / Rechazar por Cliente | Proposals Manager | Solo desde "Enviada al Cliente" | Fixture `workflow.json` |
| Crear versión nueva | Proposals Manager, System Manager | Solo desde Rechazada sin proyecto activo | `utils/proposal_versioning.py:assert_can_manage_proposals()` + `assert_can_create_new_version()` |
| Crear proyecto | Proposals Manager, System Manager | Solo en estado Ganada, submitted, no superseded | `utils/project.py:assert_can_manage_proposals()` + `assert_can_create_project()` |
| Rebuild de costos | Proposals Manager, System Manager | Protegido en scheduler diario y endpoint manual | `utils/cost_matrix.py:assert_can_manage_proposals()` |
| Quotation declarar pérdida | Todos | Bloqueado si la Quotation tiene `proposal_group` | `overrides/quotation_override.py:declare_enquiry_lost` |
| Sales Order — botón visible | Todos | Solo aparece en estado Ganada + proyecto creado | `public/js/quotation.js` línea 14 |

---

## Workflow completo (fixture)

```
Borrador (docstatus=0)
    ↓ "Enviar a Revision" (Proposals User o Manager)
En Revision (docstatus=1) ← doc queda submitted aquí
    ↓ "Aprobar"               ↓ "Rechazar"
Aprobada (docstatus=1)    Rechazada (docstatus=1) ← terminal para esa versión
    ↓ "Enviar al Cliente"
Enviada al Cliente (docstatus=1)
    ↓ "Marcar como Ganada"    ↓ "Rechazar por Cliente"
Ganada (docstatus=1)      Rechazada (docstatus=1)
```

El submit automático ocurre en la transición Borrador → En Revision porque el estado
"En Revision" tiene `doc_status: "1"` en el fixture del workflow.

---

## Decisiones relacionadas

| ADR | Tema |
|---|---|
| [ADR-0000](../adr/0000-estado-inicial-app.md) | Estado inicial y arquitectura base del app |
| [ADR-0001](../adr/0001-mvp-etapa-1-implementacion.md) | Implementación MVP y scope del RC 1.0 |
| [ADR-0002](../adr/0002-rentabilidad-estimada-propuesta.md) | Diseño del reporte de rentabilidad estimada |
| [ADR-0003](../adr/0003-sincronizacion-alcance-catalogo.md) | Sincronización controlada del alcance con el catálogo |
| [ADR-0004](../adr/0004-phase-link-proposal-phase.md) | `phase` como Link a Proposal Phase |
| [ADR-0005](../adr/0005-resolucion-congelamiento-print-format.md) | Resolución y congelamiento del Print Format comercial |
| [ADR-0006](../adr/0006-separacion-app-generica-personalizacion-privada.md) | Separación app genérica vs personalización privada por cliente |
| [ADR-0007](../adr/0007-contenido-editorial-item-y-congelamiento.md) | Contenido editorial del servicio en `Item` y congelamiento inmutable (snapshot) |
| [ADR-0008](../adr/0008-integracion-fiscal-quotation-reuso-facturacion-mexico.md) | Impuesto automático en Quotation por reutilización read-only de `facturacion_mexico` |
| [ADR-0013](../adr/0013-secciones-opcionales-por-propuesta.md) | Secciones narrativas opcionales activables por propuesta (selector + `include_by_default`) |
| [ADR-0014](../adr/0014-render-portada-separada-merge.md) | Render de portada separada + merge con pypdf (portada full-bleed + Letter Head repetido) |
