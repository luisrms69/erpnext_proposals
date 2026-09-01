# Changelog — erpnext_proposals

## [No liberado]

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
