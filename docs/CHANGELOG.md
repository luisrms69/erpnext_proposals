# Changelog — erpnext_proposals

## [No liberado]

### Added — Evaluación Económica por periodos (v0.17.0, ADR-0018 Fase 2A)
- **Comportamiento económico en catálogo, por Company:** nueva child **`Proposal Economic Behavior Rule`** en
  `Proposal Settings` (*Item/Item Group → `one_time`/`recurring`/`infrastructure` + intervalo/conteo*), con
  precedencia Item > Item Group > `one_time`. La preventa **no** clasifica líneas ni captura cadencias; el
  importe sale de la propuesta (precio de línea / costo externo), sin re-captura.
- **Plazo contractual:** `Proposal Settings.default_contract_term_months` + custom field
  `Quotation.proposal_contract_term_months` (único campo visible nuevo), **precargado y editable**; no se
  reescribe tras cambiarlo.
- **Reporte `Evaluacion Economica`** (Script Report, on-demand, no persiste): calendario relativo `Mes 0…N`
  con Ingreso / Costo externo / Costo laboral / Costo total / Margen + resumen contractual y margen %. Motor
  `utils/economic_calendar.py` **iterativo por periodo** (preparado para FX/escalamiento de Fase 2C sin
  snapshots hoy); costo laboral distribuido por la temporalidad de Scope (`floor(offset/30)` + reparto
  proporcional; milestone/duración 0 = puntual).
- **Freeze:** en Borrador → En Revisión se congela el comportamiento efectivo por línea
  (`proposal_economic_behavior/_billing_interval/_billing_interval_count` en Quotation Item;
  `economic_behavior/billing_interval/billing_interval_count` en Required Item); en submitted la evaluación usa
  **solo** el snapshot → cambios posteriores de configuración no alteran la propuesta histórica.
- **Fuera de 2A** (diferido a 2B/2C): cobros/cash flow, CAPEX financiero, FX, escalamiento, VAN/TIR/payback,
  sensibilidad; y la configuración de handoff operativo.
- **Presentación (UX):** terminología del cliente **NRC/MRC/CAPEX** (mapeo `one_time`→NRC, `recurring`→MRC,
  `infrastructure`→CAPEX; solo capa visible). Modelo enriquecido `get_economic_evaluation` (whitelisted +
  jinja method): resumen, composición por NRC/MRC/CAPEX por línea (MRC con cadencia y acumulado contractual),
  tabla de esfuerzo (Scope Items) y calendario con **trazabilidad** por componente.
- **Integración en la Quotation:** nueva pestaña **«Evaluación Económica»** (custom fields
  `proposal_economic_tab` + HTML `proposal_economic_evaluation_html`) renderizada por `quotation.js` (sin
  botones; consume el método, no duplica lógica). El campo **`Plazo contractual (meses)`** se reubicó alto en
  la pestaña Propuesta (visible).
- **Reporte ejecutivo profesional = sustitución del Print Format `Rentabilidad Estimada`:** su HTML pasa a ser
  el diseño profesional de Evaluación Económica (KPI cards, NRC/MRC/CAPEX, fuentes de costo, calendario con
  **gráfico de barras en CSS**, trazabilidad por segmentos `Mes 0`/`Mes 1`/`Meses 2-11`), consumiendo
  `get_economic_evaluation` (ya no `get_profitability_data`). **Se reutiliza** el mismo botón «Vista previa /
  Descargar rentabilidad», `render_proposal_pdf` y el adjunto oficial — **sin** crear Print Format, vista,
  preview, botón ni flujo nuevos. Diseño **agnóstico del renderer** (hex literal, sin `var()`/gradientes/JS;
  barras en CSS): valida por **wkhtmltopdf** y **Gotenberg/Chromium**. `get_economic_calendar` se vuelve
  proyección del modelo único `get_economic_evaluation`; Script Reports `Evaluacion Economica` y
  `Profitability Estimate` se conservan.
- **Hardening del motor (base para 2B/2C):** fuente **única** (`get_economic_evaluation`; `get_economic_calendar`
  la proyecta); distribución temporal en **una** función (`_distribute_over_months`). **Invariantes**
  (`_assert_reconciled` en cada evaluación): grupos/calendario/trazabilidad reconcilian a los totales o
  `EconomicEvaluationError` (nunca números inconsistentes en silencio). **Determinismo** (estructura completa
  idéntica). **Sin pérdida silenciosa de costo**: el horizonte se expande y se emite `warnings`
  (`labor_beyond_term`/esfuerzo no atribuible). Esfuerzo con datos **humanos** (actividad + **perfil**
  `designation` + horas/tarifa/fuente); costo externo con **origen** y **fuente congelada**. **Nada derivado
  se persiste** (ingreso/margen/calendario on-demand). Calendario **económico/devengado ≠ flujo de caja**
  (VPN/TIR sobre cash flow en 2C). **Estética del Print Format: pendiente.**
- Docs: `usuario/evaluacion-economica.md`, **ADR-0018** (§6 bis/6 ter/**7 bis hardening**), arquitectura y
  referencia. Tests: **56** (`test_economic_calendar.py`: agrupación NRC/MRC/CAPEX, trazabilidad,
  consistencia resumen↔calendario, invariantes, determinismo, bordes A-G/timeline, precisión, freeze).

### Added — Items requeridos y modelo económico aditivo (v0.17.0)
- **`Proposal Required Item`** (child de Quotation, campo `required_items`): Items **no vendidos** necesarios
  para cumplir la propuesta (PMO, licencias internas, hardware, partner). Campos: `item`, `qty`, `uom` +
  snapshot de costo interno. No generan ingreso ni línea comercial.
- **Alcance desde ambas fuentes:** la generación / *Agregar Scope Items desde Items* / resync iteran
  **Items vendidos ∪ Items requeridos** por el mismo resolver N:M; se conserva la clave de dedup
  `(item_code, scope_item)`.
- **Costo externo aditivo (ADR-0017):** independiente del costo laboral (se elimina el `covered_by_scope`
  que anulaba el costo de items con Scope). Gate `Item.is_purchase_item`; resolución con pricing **nativo**
  (`utils/item_cost.resolve_external_cost`: `get_item_price` de compra → `last_purchase_rate` →
  `valuation_rate`). Supplier Quotation automática queda fuera.
- **Freeze del costo externo** al pasar Borrador → En Revisión (`proposal_frozen_cost_rate/_source` +
  `proposal_cost_locked` en Quotation Item; `frozen_cost_rate/_source` + `cost_locked` en Required Item);
  el reporte lee el snapshot en documentos submitted → la rentabilidad histórica no cambia con pricing vivo.
- **Rentabilidad:** ingresos − costo de compra (vendidos/requeridos comprables) − costo de esfuerzo.
- **Precarga por configuración, por Company (Fase 1 bis):** nuevo DocType **`Proposal Settings` — uno por
  `Company`** (no Single; editable por `System Manager` / `Proposals Manager`; máximo uno por Company) con
  reglas **`Proposal Required Item Rule`** (*Item/Item Group vendido → Item requerido*, con precedencia de
  Item sobre Item Group) y **`default_procurement_scope_item`**. La Quotation resuelve la configuración de
  forma **estricta por `quotation.company`**: sin settings para esa Company no hay precarga ni abastecimiento
  y **no hay fallback global**. Al agregar Items vendidos **nuevos**, se precargan los Items requeridos
  configurados (`auto_generated=1`) y sus Scope Items; todo Item **comprable** (vendido o requerido) suma el
  Scope Item de **abastecimiento**, con opt-out por Item (**custom field `Item.proposal_skip_procurement`**).
  Es solo precarga: no duplica, no repone borrados y se preserva en el resync.
- Docs: `usuario/items-requeridos.md`, **ADR-0017** (supersede parcial de ADR-0002; sección Fase 1 bis),
  arquitectura y referencia regeneradas.

### Added — SOW como tercer documento oficial (v0.16.0)
- **`Proposal Template.sow_print_format`** (Link → Print Format, opcional): define el Print Format del
  **SOW** (Statement of Work) de esa familia de propuesta. Vacío = no se genera SOW.
- **Resolver genérico** `resolve_sow_print_format` + `get_effective_sow_print_format` (whitelisted): el
  SOW es **otra representación del mismo contenido congelado** de la Quotation — mismo `render_proposal_pdf`,
  mismo snapshot/freeze, misma protección histórica; solo cambia el Print Format.
- **SOW como tercer documento oficial:** `attach_proposal_pdfs` adjunta, al pasar **Borrador → En Revisión**,
  propuesta comercial + rentabilidad + **SOW** (privados e inmutables), cuando la plantilla define `sow_print_format`.
- **Portada separada generalizada:** `_uses_separate_cover` deja de reconocer solo el Print Format comercial;
  ahora aplica a **cualquier documento oficial designado por la plantilla** (comercial o SOW) cuando el flag
  existente **`separate_cover_page`** está activo — sin ramas por tipo ni nombres hardcodeados.
- **Acciones de borrador** (whitelisted): `download_sow_draft_pdf` y `download_rentabilidad_draft_pdf`
  (espejo de `download_commercial_draft_pdf`).
- **Botones (grupo Propuesta), nomenclatura inequívoca:** `Vista previa comercial`, `Descargar PDF comercial`,
  `Vista previa rentabilidad`, `Descargar PDF rentabilidad`, `Vista previa SOW`, `Descargar PDF SOW`.
- El loader de catálogos carga `sow_print_format` en el Proposal Template.

### Added — Relación N:M Item ↔ Scope Item (v0.15.0)
- Relación **N:M** entre `Item` y `Scope Item`: child table `Scope Item.erpnext_items` (DocType
  `Scope Item ERPNext Item`) + resolver central `resolve_scope_items_for_item` que une child y el Link
  legacy `erpnext_item` (sin backfill ni patch, compatible en lectura). Un Scope Item puede aplicar a
  varios Items y un Item tener varios Scope Items — ver ADR-0016.
- Administración desde el formulario **Item** (botón *Scope Items* → `get/set_scope_items_for_item`):
  solo selecciona Scope Items habilitados; aislamiento por Item al quitar.
- El **loader de catálogos** carga la relación por set con `"erpnext_items": [...]` por Scope Item
  (ausente=no toca, presente=sincroniza, vacía=limpia; valida duplicados; Items inexistentes → `pending`).
- Generación de alcance en Quotation **solo para líneas de Item nuevas**; un guardado normal no repuebla;
  acción manual *Agregar Scope Items desde Items* para recuperar faltantes; el resync ya **no** agrega.

### Docs — N:M (v0.15.0)
- `usuario/scope-items-reutilizables.md` (nueva), `usuario/crear-propuesta.md`, `tecnico/arquitectura.md`,
  referencia autogenerada (`doctypes`, `api`, `hooks`), y **ADR-0016** (relación N:M lectura-compatible).

### Added
- Impuesto automático en Quotation reutilizando **por import** (read-only) la resolución fiscal de
  `facturacion_mexico` (Centro de Costos → Branch → zona → STCT). Adapter exclusivo en
  `erpnext_proposals` (`utils/quotation_tax.py`, hook `Quotation.before_validate`); `facturacion_mexico`
  **no se modifica**. Solo aplica con `quotation_to == "Customer"`; no-op suave si falta configuración;
  respeta selección manual de `taxes_and_charges`; sin la validación SAT estricta de Sales Invoice —
  ver ADR-0008.
- Resolución del Print Format comercial (override → Proposal Template → default) con congelamiento
  del formato efectivo — ver ADR-0005.
- Loader genérico de catálogos por ruta externa y separación app-genérica vs personalización privada
  por cliente — ver ADR-0006.

### Docs
- `tecnico/print-formats.md`: sección de resolución y congelamiento del formato comercial; `hide_title`
  y estructura del snapshot de secciones; convención del umbral `sequence >= 500` sin referirse a
  templates "instalados".
- `tecnico/arquitectura.md`: loader de catálogos (incluye Items, Print Formats y Payment Terms /
  Payment Terms Templates); modelo de contenido editorial en `Item` y su copia congelada en
  `Quotation Item`; `hide_title` en `Proposal Template Section`; los Templates/Sections se cargan por
  catálogo, **no** por `install.py`.
- `tecnico/setup.md`, `tecnico/despliegue-produccion.md`, `usuario/flujo-operativo.md`: corregido que
  `after_install` **no** siembra contenido comercial (solo Desktop Icon); el contenido se carga con el
  loader del catálogo. `facturacion_mexico` agregado como `required_app`.
- ADR-0005 y ADR-0006.

## [0.10.0] — 2026-08-26

### Added
- **Letter Head explícito por plantilla:** `Proposal Template.letter_head` (Link → `Letter Head`,
  opcional) selecciona el encabezado de marca por **nombre**; `sync_letter_head_from_template`
  (`utils/print_format.py`, en `on_quotation_validate`) lo copia al campo nativo `Quotation.letter_head`
  al aplicar/cambiar la plantilla o si está vacío, sin pisar una selección manual — independiente del
  default del sitio.
- **Portada separada opcional + merge determinista:** `Proposal Template.separate_cover_page` (Check,
  default `0`). Cuando está activo y se renderiza el Print Format comercial, `render_proposal_pdf`
  (`utils/print_format.py`, cableado en `utils/quotation.py::_attach_pdf`) produce el PDF en **dos
  renders unidos con pypdf** (portada `no_letterhead`, 1 página; cuerpo con Letter Head repetido +
  footer). El modo se pasa por `doc.proposal_render_part` (`'cover'`|`'body'`) que solo consume el
  Print Format; **sin** monkey-patch a `get_pdf`, **sin** tocar Frappe core, **sin** afectar otros
  Print Formats. Fallback backward-compatible a un solo render sin la marca u otro formato — ver
  ADR-0014.
- **Paginación por sección:** `Proposal Template Section.page_break_before` (Check, default `0`;
  `1` = la sección inicia página nueva; independiente de `is_executive_summary`).
- **Helpers Jinja genéricos de impresión/numeración** (`utils/printing.py`, registrados en `hooks.py`):
  `keep_headings_with_next` (evita headings huérfanos vía `page-break-inside:avoid`),
  `section_number` (número de capítulo dinámico por nombre, para referencias cruzadas) y `service_item`
  (resuelve el Quotation Item "de servicio" sin hardcodear `item_code`).
- **Metadata de servicio en `Item`** (3 Custom Fields, Data, opcionales, genéricos, SSOT):
  `proposal_service_validity`, `proposal_min_unit`, `proposal_service_hours`.
- **Loader del catálogo — capacidad v9** (`catalog_data/catalog_loader.py`): nueva clave `letter_heads`
  (siembra idempotente por `letter_head_name`; nunca `is_default=1`, el catálogo es dueño de
  `is_default=0` para selección explícita por nombre); soporte de los campos nuevos del Template
  (`letter_head`, `separate_cover_page`) en crear/diff/update y de los 3 campos de servicio del Item.
  `LOADER_CAPS_VERSION` sube 8 → 9; `capabilities()` expone `letter_heads`.

### Docs
- Nueva **ADR-0014** (render de portada separada + merge con pypdf; relacionada con ADR-0005 y
  ADR-0006).
- `tecnico/print-formats.md`: sección de render de portada separada (`render_proposal_pdf`,
  `separate_cover_page`, `doc.proposal_render_part`, merge pypdf, fallback), selección de Letter Head
  (`Proposal Template.letter_head` → `Quotation.letter_head`), helpers
  `keep_headings_with_next`/`section_number`/`service_item` y `page_break_before`.
- `tecnico/arquitectura.md`: campos nuevos de `Proposal Template` (`letter_head`, `separate_cover_page`),
  `Proposal Template Section.page_break_before`, metadata de servicio en `Item` y capacidad v9 del
  loader (`letter_heads`).
- `usuario/campos-principales.md`: campos de usuario "Letter Head", "Portada separada" y
  "Page Break Before".

## [0.0.1] — 2026-05-18

### Added
- Scaffold inicial del app
- Estructura de documentación (docs/adr/)
- Configuración Claude Code (.claude/)
- Site de desarrollo: proposals.dev
- Site de tests: test-erpnext_proposals.localhost
