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
| Print Formats | PDF comercial (default genérico) y Rentabilidad Estimada (privado); helpers Jinja | `print_format/`, `utils/printing.py` | Activo |
| Resolución de Print Format | Cadena override→template→default y congelamiento del efectivo (ADR-0005) | `utils/print_format.py` | Activo |
| Loader de catálogos | Carga genérica e idempotente por ruta externa: Proposal Phases, Sections, Items (+ campos editoriales), Scope Items, Proposal Templates, Print Formats y **Payment Terms / Payment Terms Templates** (ADR-0006) | `catalog_data/catalog_loader.py` | Activo |
| Reporte de rentabilidad | Fuente de datos compartida entre UI y Print Format | `report/profitability_estimate/` | Activo |
| Override de Quotation | Bloquea `declare_enquiry_lost` en propuestas con workflow | `overrides/quotation_override.py` | Activo |
| Sales Order hooks | Propaga proyecto y cost center de Quotation a SO | `utils/sales_order.py` | Activo |

---

## Flujos principales

| Flujo | Entrada | Proceso | Salida | Docs relacionados |
|---|---|---|---|---|
| Creación de propuesta | Nueva Quotation con `proposal_group` | `before_insert` valida grupo único; `validate` genera scope items desde catálogo (**append-only**: solo agrega combinaciones `(item, scope_item)` faltantes; no actualiza ni elimina filas existentes), **congela el contenido editorial del `Item` en cada `Quotation Item`** (`_copy_item_proposal_fields`, solo líneas nuevas) y captura el `proposal_sections_snapshot` de las Proposal Sections **únicamente si está vacío** (un guardado normal posterior **no** lo regenera ni relee los maestros). También sincroniza `proposal_print_format` desde el Template (`sync_proposal_print_format_from_template`) | Quotation en Borrador con scope, contenido de Item congelado y snapshot de secciones capturado | `utils/quotation.py` |
| Sincronizar alcance desde catálogo | Botón (solo Borrador) → `resync_scope_from_catalog` | **update + remove + add** sobre filas `auto_generated=1`: refresca campos controlados por catálogo, elimina las sin respaldo (Scope Item deshabilitado/borrado o Item quitado) y agrega nuevas; preserva `include_in_proposal` y filas manuales (`auto_generated=0`). También **regenera** el `proposal_sections_snapshot` desde los maestros vigentes — es la **única** vía de actualizar el snapshot, y solo mientras la propuesta siga en Borrador | Alcance y snapshot de secciones sincronizados con el catálogo vigente | `utils/quotation.py` |
| Avance a En Revision | Workflow action "Enviar a Revision" | `validate_workflow`: valida campos, **conserva** el `proposal_sections_snapshot` ya capturado en Borrador (lo crea como fallback solo si viene un Borrador legacy sin snapshot), **congela las tarifas de costo** (idempotente por fila; también se aplica en el Submit de respaldo), genera y adjunta PDFs | Quotation submitted (docstatus=1), snapshot de secciones inmutable, tarifas congeladas, PDFs adjuntos | `utils/workflow_validations.py` |
| Aprobación / Rechazo | Workflow action "Aprobar" o "Rechazar" | Registra `reviewed_by`, `reviewed_on`; si aprobada: registra `approved_by`, `approved_on` | Quotation en Aprobada o Rechazada con trazabilidad | `utils/workflow_validations.py` |
| Versionado | Quotation Rechazada + acción "Crear nueva versión" | Copia campos a nueva Quotation (incluye el `proposal_sections_snapshot` **literal**, el contenido congelado de cada `Quotation Item` y el `proposal_specific_scope` manual de cada línea, editable de nuevo en el Borrador nuevo); marca original como `superseded_by_proposal`; bloquea si hay proyecto activo en la versión anterior. **Regenera** el payment schedule válido para la nueva `transaction_date` (`_resolve_new_version_payment` / `_is_automatic_single_row`), no copia fechas viejas | Nueva Quotation en Borrador vinculada | `utils/proposal_versioning.py` |
| Marcar como Ganada | Workflow action "Marcar como Ganada" | Transición Enviada al Cliente → Ganada | Quotation en estado Ganada; habilita botón Crear Proyecto y Sales Order | `fixtures/workflow.json` |
| Crear proyecto | Botón "Crear/Ver Proyecto" (estado Ganada) | Crea Project + Tasks desde scope items; idempotente: reutiliza proyecto si ya existe | Proyecto ERPNext con Tasks vinculadas a scope items | `utils/project.py` |
| Propagación a Sales Order | Creación de SO desde Quotation Ganada | `validate` y `on_submit` propagan `proposal_project` y `proposal_cost_center` al SO | SO con proyecto y cost center heredados | `utils/sales_order.py` |
| Rebuild de costos | Scheduler diario o acción manual | Lee Activity Cost, Timesheets, Salary Assignments; upsert en Proposal Cost Matrix | Matriz actualizada; Log de cambios de tasa | `utils/cost_matrix.py` |

---

## DocTypes críticos

| DocType | Propósito | Relaciones | Notas |
|---|---|---|---|
| `Proposal Section` | Bloque de texto narrativo reutilizable | Referenciado por `Proposal Template Section` | Tiene flag `is_executive_summary` para resaltar en portada |
| `Proposal Template` | Agrupa secciones en orden para un tipo de proyecto | Tiene child table `Proposal Template Section` | Se cargan desde el **catálogo** (loader), **no** por `install.py` (ADR-0006) |
| `Proposal Template Section` | Fila de sección en un template | Link a `Proposal Section`; soporte para `custom_title` y `custom_content`; **`hide_title`** (Check, oculta el heading por Template); **`include_by_default`** (Check, default `1`; en `0` la sección es opcional por propuesta) | Child table de `Proposal Template` |
| `Proposal Optional Section` | Fila del selector de secciones opcionales activadas en una Quotation | Child de `Quotation` (custom field `proposal_optional_sections`, Table MultiSelect → `Proposal Section`) | Solo activa filas del Template marcadas `include_by_default=0`; se congela vía `proposal_sections_snapshot` (ver ADR-0013) |
| `Scope Item` | Actividad del catálogo maestro | Link a `Item` de ERPNext (`erpnext_item`); `phase` **Link a `Proposal Phase`** | Sin precio; describe trabajo, perfil y horas estimadas. El **contenido editorial** del servicio (metodología, resultado esperado, límite del alcance) vive en el **Item**, no aquí |
| `Quotation Scope Item` | Copia congelada de un Scope Item dentro de una Quotation | Parent: `Quotation`; link a `Scope Item`, `Task` y `phase`→`Proposal Phase` | Child table; `rate_locked` se fija en transición a En Revision. Flags: `include_in_proposal` (visible en PDF) y `is_internal_cost_task` (tarea interna: entra en costo/rentabilidad, se excluye del PDF comercial) |
| `Item` (extendido) | Contenido comercial del servicio | Custom fields editoriales administrados por el catálogo | `proposal_content_section`, `proposal_methodology`, `proposal_expected_result`, `proposal_scope_limit` — descripción/metodología/resultado/límite del servicio |
| `Quotation Item` (extendido) | Copia **congelada** del contenido editorial del Item dentro de la Quotation | Child de `Quotation` | `proposal_methodology`, `proposal_expected_result`, `proposal_scope_limit` copiados del Item al generar el alcance; el PDF usa esta copia y **no** relee el Item maestro. Además `proposal_specific_scope` (Text Editor): **alcance contratado manual** por línea — editable en Borrador, **no** viene del Item/catálogo (ver [ADR-0010](../adr/0010-alcance-especifico-contratado-quotation-item.md)) |
| `Proposal Phase` | Catálogo de fases (`phase_code`, `phase_name`, `sequence`) | Referenciado por `phase` en Scope Item / Quotation Scope Item | El orden en propuesta/reportes/Tasks usa `sequence`; el display usa `phase_name`. Helpers en `utils/phase.py` (`phase_label`, `order_phases`, jinja methods) |
| `Proposal Cost Matrix` | Costos por (Designation, Activity Type) | Alimenta freeze de costos en scope items | Rebuildeado diariamente; `is_general_rate=1` para filas de promedio por designación |
| `Proposal Cost Matrix Log` | Historial de cambios de tasa | Parent: ninguno | Append-only; creado por `cost_matrix.py` en cada cambio de tasa |
| `Quotation` (extendido) | Documento central; extendido con ~30 custom fields | Tiene child `Quotation Scope Item`; link a `Project` | Custom fields en fixture; extended class via `QuotationProposalMixin` |

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
| `phases` | `Proposal Phase` | `phase_code` | `_seed_phases` |
| `sections` | `Proposal Section` | `section_name` | `_seed_sections` |
| `items` | `Item` (+ campos editoriales de propuesta) | `item_code` | `_seed_items` |
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
- **`dry_run`:** previsualiza (Creados / Sin cambios / Actualizados / Conflictos) sin escribir.
- **Nunca borra:** 0 `delete_doc` en el código.
- **Print Formats protegidos:** `Propuesta Comercial` y `Rentabilidad Estimada` (assets del repo
  público) están en `PROTECTED_PRINT_FORMATS`; el loader los reporta como conflicto y **nunca** los
  escribe (ADR-0005/0006).
- **`capabilities()`:** declara la versión de capacidades del loader; el instalador del kit la verifica
  para exigir que el código del app en el bench destino soporte lo que el catálogo usa.

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
| Frappe `File` | Almacenamiento de PDFs generados | `utils/quotation.py` — `attach_proposal_pdfs()` | PDF público: Propuesta Comercial; privado: Rentabilidad Estimada. `get_proposal_documents_status()` (whitelisted) comprueba su existencia real (por prefijo de nombre, por el hash de `save_file`) para que el botón `Propuesta` (JS) oculte la acción de **re-generar** cada documento oficial una vez adjunto, sin quitar el acceso a los ya generados. Cada PDF oficial se marca con el Custom Field **`File.is_proposal_official_document`** (read-only, solo lo fija `_attach_pdf`) y su **borrado queda protegido** por `doc_events[File].on_trash` (`utils/official_document_protection.py`): ni usuarios ordinarios ni System Manager pueden eliminarlo, solo `Administrator` y el propio flujo de regeneración (flag `INTERNAL_REPLACE_FLAG`); persiste tras cancelar; no afecta otros adjuntos ni la descarga. Ver **ADR-0012** |
| Frappe Realtime | Notificación al cliente JS cuando PDFs están listos | `utils/quotation.py` — `frappe.publish_realtime()` | Evento: `erpnext_proposals_pdfs_attached` |
| `facturacion_mexico` (impuestos) | Impuesto automático en Quotation reutilizando la resolución fiscal existente | `utils/quotation_tax.py` — `apply_fiscal_taxes` (hook `Quotation.before_validate`) | **Read-only sobre `facturacion_mexico`** (solo `import`); ver abajo y **ADR-0008** |
| ERPNext `Contact` | Resolución y persistencia del contacto dirigido de la Quotation | `utils/quotation_contact.py` — `set_proposal_contact` (hook `Quotation.before_insert`), `autocorrect_missing_contact` (hook `Quotation.validate`) | Reúso nativo `get_default_contact`/`get_contact_details`; ver abajo y **ADR-0009** |
| Frappe CRM `CRM Deal` (opcional) | Contacto del Deal como autoritativo al crear la Quotation | `utils/quotation_contact.py` — `_deal_primary_contact` | Lectura **desacoplada** (guardada por `frappe.db.exists`); sin dependencia del app `crm` |

### Materialización de dependencias en Tasks del Project

Al crear el Project (`utils/project.py`), las filas `Task Depends On` de las Tasks resultantes provienen
de **dos capas** — importante para conciliar el conteo, porque el total supera al número de
dependencias fuente:

1. **Dependencias de negocio (el app) — hija→hija:** `_resolve_native_dependencies` traduce los códigos
   de dependencia **congelados** en cada `Quotation Scope Item` a relaciones `depends_on` **hija→hija**,
   solo cuando **ambas** Tasks están contratadas (predecesor incluido), con dedup e idempotencia. Su
   número es exactamente el de las aristas fuente **entre los scope items contratados** (un subconjunto
   del total del catálogo: contratar menos Items reduce este número).
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
