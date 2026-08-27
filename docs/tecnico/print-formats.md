# Print Formats — Desarrollo y mantenimiento

Guía técnica de los Print Formats del app:

- **Propuesta Comercial** — PDF comercial **genérico** que ships el app (sin branding; el logo
  se hereda de `Company.company_logo`). Es el *default* del sistema.
- **Rentabilidad Estimada** — PDF interno de análisis de costos.

> **Formatos específicos de cliente (branded) son datos privados y viven fuera del repo.**
> El app solo versiona el formato genérico. Ver [ADR-0006](../adr/0006-separacion-app-generica-personalizacion-privada.md).

---

## Resolución del Print Format comercial

Qué formato se usa al imprimir la propuesta comercial se resuelve por una **cadena de precedencia**
(módulo `utils/print_format.py`). Ver [ADR-0005](../adr/0005-resolucion-congelamiento-print-format.md).

**En Borrador (resolución dinámica)** — `dynamic_commercial_print_format(doc)`:

1. **Override por Quotation** — campo `proposal_print_format` (Link a Print Format, editable en Borrador).
2. **Default por Proposal Template** — campo `Proposal Template.print_format`.
3. **Default del app** — `DEFAULT_COMMERCIAL_PRINT_FORMAT = "Propuesta Comercial"`.

El primero que exista, gana. Vacío → baja al siguiente nivel.

**Congelamiento** — al pasar de Borrador a *En Revisión* (freeze), `freeze_effective_print_format(doc)`
persiste el formato resuelto en `proposal_effective_print_format` (read-only, `no_copy`, **inmutable**).
Desde ese momento `resolve_commercial_print_format(doc)` devuelve **siempre** el formato congelado,
sin volver a resolver. Una **nueva versión** hereda ese formato como override editable.

| Función (`utils/print_format.py`) | Rol |
|---|---|
| `resolve_commercial_print_format(doc)` | congelada → el congelado; Borrador → resolución dinámica |
| `dynamic_commercial_print_format(doc)` | cadena override → template → default |
| `sync_proposal_print_format_from_template(doc)` | al aplicar/cambiar el Template (o si el override está vacío), **puebla** `proposal_print_format` con el formato del Template; corre en `validate` de la Quotation |
| `freeze_effective_print_format(doc)` | persiste el efectivo al congelar (idempotente) |
| `validate_print_format(name)` | valida que el formato sea usable para Quotation (existe, doc_type, no disabled) |
| `assert_assignable_print_format(doc, fieldname)` | validación **change-aware** de servidor compartida (Quotation `proposal_print_format` + Proposal Template `print_format`): bloquea ADOPTAR un formato no elegible; no re-valida referencias no modificadas (protege históricos) |
| `get_proposal_print_formats(...)` | whitelisted; **query central** del campo Link (elegibilidad única: `doc_type=Quotation`, `disabled=0`) |
| `get_print_format_status(name)` | whitelisted; estado (`ok`/`missing`/`disabled`/`wrong_doctype`) para el warning de referencia obsoleta |
| `get_effective_commercial_print_format(quotation)` | whitelisted; lo usa el botón *Imprimir Propuesta Comercial* (JS) |

El mismo resolver se usa en el snapshot de impresión y al adjuntar el PDF comercial, de modo que
todos los caminos de impresión coinciden en el formato efectivo.

### Logo del PDF

El logo del formato se hereda de `Company.company_logo` (sin branding hardcodeado). Dos helpers Jinja
en `utils/printing.py` lo exponen:

- `get_logo_url(...)` — URL/ruta del logo para usar en `<img src>`.
- `get_logo_data_uri(logo_path)` — el logo **embebido como data URI** (base64), útil cuando el motor de
  PDF no resuelve rutas relativas o el archivo debe viajar dentro del HTML.

---

## Regla de producción

**Nunca editar un Print Format directamente en ERPNext UI como cambio permanente.**

Si se prueba algo en UI → replicar en el JSON → commit → PR.

Los JSONs en Git son siempre la fuente de verdad:
- `erpnext_proposals/print_format/propuesta_comercial/propuesta_comercial.json`
- `erpnext_proposals/print_format/rentabilidad_estimada/rentabilidad_estimada.json`

---

## Flujo obligatorio para cambios

```
1. Crear rama feature/print-*
2. Editar solo el JSON del Print Format (CSS/HTML/Jinja)
3. Recargar el formato en el site:
   bench --site proposals.dev execute "frappe.reload_doc('ERPNext Proposals', 'Print Format', '<Nombre>', force=True)"
4. Generar PDF de prueba y revisar visualmente
5. Commit con prefijo style(print): o feat(print):
6. Guardar PDF de evidencia en working_docs/archive/visual-regression/<formato>/
7. PR con PDF adjunto en la descripción
8. Merge
9. En producción:
   bench --site <site> execute "frappe.reload_doc('ERPNext Proposals', 'Print Format', '<Nombre>', force=True)"
```

---

## Comandos de recarga por formato

```bash
# Propuesta Comercial
bench --site proposals.dev execute \
  "frappe.reload_doc('ERPNext Proposals', 'Print Format', 'Propuesta Comercial', force=True)"

# Rentabilidad Estimada
bench --site proposals.dev execute \
  "frappe.reload_doc('ERPNext Proposals', 'Print Format', 'Rentabilidad Estimada', force=True)"
```

---

## Anatomía del PDF — Propuesta Comercial

El Print Format `Propuesta Comercial` renderiza en un **orden fijo de bloques**. El contenido
narrativo proviene de las secciones del template (`Proposal Template Section`), pero el
**alcance** (Scope Items) y la **inversión** (líneas de la cotización) se insertan en
posiciones fijas del Jinja, **no** como secciones del template.

Orden de render:

| # | Bloque | Origen del contenido |
|---|---|---|
| 1 | Portada | Datos de la cotización + logo |
| 2 | Resumen Ejecutivo | Sección con `is_executive_summary = 1` |
| 3 | Índice | Generado automáticamente |
| 4 | Secciones narrativas | Secciones del template con **`sequence < 500`** |
| 5 | **Plan de Trabajo** | **Scope Items** (`quotation_scope_items`), agrupados por fase |
| 6 | **Entregables** | Scope Items que tienen `deliverable` |
| 7 | **Inversión** | Líneas de la cotización (`doc.items`) |
| 8 | Secciones legales / comerciales | Secciones del template con **`sequence >= 500`** |
| 9 | Bloque de aceptación | Espacio de firma |

### Regla del umbral `sequence >= 500`

El número **500** es el umbral que decide **dónde** aparece una sección del template respecto
al alcance y la inversión:

- Sección con `sequence < 500` → se renderiza **antes** del Plan de Trabajo (bloque 4).
- Sección con `sequence >= 500` → se renderiza **después** de la Inversión (bloque 8).

Es una convención definida en el Jinja de `propuesta_comercial.json` (buckets
`body_sections` / `late_sections`). Los Proposal Templates provienen del **catálogo** (no se
instalan con la app); cada Template decide, por la `sequence` de sus secciones, cuáles caen
**antes** del alcance (`sequence < 500`) y cuáles **después** de la Inversión (`sequence >= 500`).

**Para colocar una sección después de la Inversión** —por ejemplo términos legales, garantías
o condiciones comerciales— asignarle `sequence >= 500` en el `Proposal Template Section`.

> El umbral 500 vive únicamente en el Jinja del Print Format. Al editar templates, respetar
> esta convención — de lo contrario una sección "legal" aparecerá en medio del cuerpo.

### Estructura de la entrada del snapshot y `hide_title`

Cada entrada congelada en `proposal_sections_snapshot` (ver `_build_sections_snapshot`) tiene:
`sequence`, `title`, `content` (Jinja crudo), `source_section`, `is_executive_summary`,
**`hide_title`** y `captured_on`.

`hide_title` es una **propiedad opcional de presentación por Template** que vive en
`Proposal Template Section` (Check, default `0`), no en `Proposal Section` — la misma Section
canónica puede mostrar su heading en un Template y ocultarlo en otro sin duplicarse. Se **congela**
en el snapshot al capturar, de modo que cambios posteriores del Template no alteran PDFs históricos;
el versionamiento la copia literalmente y el resync en Borrador la actualiza desde el Template.

Semántica en el Print Format (`render_section`): `hide_title = 1` → **no** se renderiza el
`block-title` (el `block-body` sí); `0` o **ausente** → se muestra el heading (comportamiento
histórico). Es una decisión genérica basada exclusivamente en `hide_title`, sin depender de
`source_section`, título, nombre, `sequence`, posición ni `is_executive_summary`.

Compatibilidad: `hide_title` **no** es campo requerido en `get_sections_snapshot`; los snapshots
históricos sin la propiedad siguen siendo `valid=True` y muestran su heading como hasta ahora.

---

## Render de portada separada + merge (portada full-bleed + Letter Head repetido)

Cuando una `Proposal Template` marca **`separate_cover_page = 1`** y se renderiza su Print Format
comercial, el PDF se produce en **dos renders unidos con el merger nativo de Frappe (pypdf)**, sin
rasterizar y sin postproceso externo. La orquestación vive en **`render_proposal_pdf(doc,
print_format)`** (`utils/print_format.py`), cableada desde `utils/quotation.py::_attach_pdf`. Ver
[ADR-0014](../adr/0014-render-portada-separada-merge.md).

Motivo: un encabezado corrido (Letter Head repetido en todas las páginas) exige un **margen superior
uniforme** que es incompatible con una **portada full-bleed a sangre** en la misma pasada. Separar
portada y cuerpo y unirlos con pypdf reconcilia ambos.

| Render | Qué emite | Letter Head | Páginas |
|---|---|---|---|
| 1 — Portada | Solo la portada (margen superior cero) | **Sin** Letter Head (`no_letterhead`) | Se toma **solo la primera** |
| 2 — Cuerpo | Todo el cuerpo + footer | Letter Head **repetido en todas** las páginas | Todas |

**Selector de modo de render — `doc.proposal_render_part`:** el modo se pasa por un atributo efímero
del propio `doc` (`'cover'` | `'body'`) que **solo el Print Format consume** para decidir qué bloque
emitir y si lleva Letter Head. **No** hay monkey-patch a `get_pdf`, **no** se toca Frappe core, **no**
se afecta ningún otro Print Format.

**Fallback backward-compatible:** cualquier plantilla **sin** la marca `separate_cover_page`, o
**cualquier otro Print Format** (p. ej. `Rentabilidad Estimada`), usa **un solo render** con el
comportamiento estándar de siempre. La ruta de dos renders solo se activa con la marca **y** el Print
Format comercial de esa plantilla.

### Selección del Letter Head (explícita por nombre)

El Letter Head del cuerpo se elige **explícitamente por nombre** en la plantilla y se copia al campo
nativo de la Quotation:

- **`Proposal Template.letter_head`** (Link → `Letter Head`, opcional) declara el encabezado de marca
  de esa familia de propuesta.
- **`sync_letter_head_from_template`** (`utils/print_format.py`, llamada desde `on_quotation_validate`)
  copia ese valor al campo **nativo `Quotation.letter_head`** al aplicar/cambiar la plantilla o si el
  campo está **vacío**. **No pisa** una selección manual del usuario.

Así el Letter Head es **explícito por nombre** e independiente del default del sitio. El render del
cuerpo usa ese Letter Head; la portada se emite `no_letterhead`.

### Helpers Jinja de paginación y numeración (`utils/printing.py`)

Métodos Jinja **genéricos** registrados en `hooks.py`, consumidos por el Print Format comercial:

| Helper | Qué hace |
|---|---|
| `keep_headings_with_next(html)` | Envuelve cada heading (`h1`–`h6`) junto con su siguiente elemento hermano en un `<div class="keep-with-next">` con `page-break-inside:avoid`, para que un título/subtítulo no quede **huérfano** al final de página. Necesario porque wkhtmltopdf **ignora** `page-break-after:avoid` en headings pero **sí respeta** `page-break-inside:avoid` en un bloque. Genérico y **no lanza**: ante error devuelve el HTML original. |
| `section_number(doc, section_identifier)` | Número de capítulo (1..N) **dinámico** de una Section por su nombre, derivado del mismo conjunto ordenado que el índice; `''` si no es visible. Para **referencias cruzadas** siempre dinámicas. |
| `service_item(doc)` | Resuelve de forma **genérica** el Quotation Item "de servicio" de la propuesta (por asociación con `quotation_scope_items`, o único con campos editoriales poblados; `None` si es ambiguo). **Sin hardcodear** `item_code`. |

### Paginación por sección — `Proposal Template Section.page_break_before`

**`page_break_before`** (Check en `Proposal Template Section`, default `0`) controla la paginación por
Template: `1` = la sección **inicia página nueva**; `0` = **fluye** tras la anterior. Es
**independiente** de `is_executive_summary`.

---

## Convención de nombres para evidencia visual

Los PDFs de evidencia se guardan en `working_docs/archive/visual-regression/<formato>/`:

```
propuesta-comercial-<componente>-v<version>.pdf
propuesta-comercial-baseline-<YYYY-MM-DD>.pdf

rentabilidad-estimada-<componente>-v<version>.pdf
rentabilidad-estimada-baseline-<YYYY-MM-DD>.pdf
```

Ejemplos:
```
propuesta-comercial-baseline-2026-05-21.pdf    ← estado completo al cerrar la rama
propuesta-comercial-investment-v1.pdf          ← sección Inversión, primera versión
rentabilidad-estimada-baseline-2026-05-21.pdf  ← baseline con tabla Alcance Cotizado
```

---

## Candado de Print Formats históricos

Una vez que una propuesta se congela, `proposal_effective_print_format` guarda el **nombre** del
formato usado, pero **no** su HTML. La reimpresión usa el HTML **actual** de ese formato. Para que
modificar un formato no altere retrospectivamente propuestas ya emitidas, un candado
(`utils/print_format_protection.py`, vía `doc_events` sobre `Print Format`) bloquea sobre un formato ya
**histórico** —referenciado por `proposal_effective_print_format` de alguna propuesta formalizada— las
operaciones que alterarían su reimpresión: **modificación** de campos de presentación, **`disabled`**,
**rename** y **delete**. Es **idempotente** (re-guardar contenido idéntico —p. ej. el loader del pack—
no se bloquea) y **sin excepción administrativa**. La evolución se hace **creando un formato nuevo con
otro nombre** y asignándolo a las propuestas futuras (`Proposal Template.print_format`). Ver **ADR-0011**.

---

## Versionamiento operativo de Print Formats

En operación cotidiana los `Proposal Template` los mantienen **usuarios** (no solo el pack). Cada
cambio de presentación se hace **creando un Print Format nuevo** (no se modifica el histórico), en
línea con ADR-0011 (que **no** se relaja).

**Convención de nombres** (la fecha es la entrada en vigor):

```
<Familia> — YYYY-MM-DD — Vn
Ejemplo:  Propuesta de Servicios Profesionales — 2026-08-12 — V1
Otra revisión el mismo día:  … — 2026-08-12 — V2
```

> No hay (todavía) resolución automática por familia: cada `Proposal Template` apunta **explícitamente**
> a un Print Format concreto.

**Flujo operativo:**

1. Crear el nuevo Print Format con nombre versionado (`disabled = 0`, `doc_type = Quotation`).
2. Dejar **intacto** el formato anterior.
3. Marcar el anterior `disabled = 1`.
4. Los selectores de `Quotation.proposal_print_format` y `Proposal Template.print_format` dejan de
   ofrecer el anterior (query central).
5. Los `Proposal Template` que aún apunten al anterior muestran un **warning** (no se reemplaza el
   valor automáticamente) hasta que un usuario elija la versión vigente.
6. Las propuestas **congeladas** conservan su formato efectivo histórico (por el PDF oficial adjunto +
   `proposal_effective_print_format`).

### Aplicación por el loader del pack (`catalog_data/catalog_loader.py`)

Cuando el catálogo declara el versionamiento (clave `print_format_versions`), el loader garantiza dos
propiedades para que el ciclo sea **idempotente** y **seguro**:

- **Dueño único de `disabled`:** para un formato listado como `supersedes`, `_seed_print_formats` **no**
  gestiona su campo `disabled`; el único que lo cambia es `_seed_print_format_versions`
  (`disable_superseded`). Así ambos seeders no se pelean el flag (evita el flip-flop que rompería la
  idempotencia). *(Declarar el anterior con `disabled: 1` en `print_formats` es además lo consistente.)*
- **Guard histórico:** si el catálogo intentara cambiar la **presentación** (`html`/`css`/…) de un
  Print Format ya **histórico**, el loader lo reporta como **`conflict`** en `--dry-run` (no como
  "actualizado"), antes de que ADR-0011 lo bloquee en el `save` del `--apply`. `disabled` no es
  presentación → sí se permite. La vía correcta sigue siendo **crear una versión nueva**.

### Selector central + validación (elegibilidad única)

Un Print Format es **elegible** para propuestas si `doc_type = "Quotation"` **y** `disabled = 0`. Ese
criterio vive en **un solo lugar** (`utils/print_format.py`) y lo comparten:

- **Query del campo Link** `get_proposal_print_formats` → conectada por `set_query` a **ambos** campos
  (`Quotation.proposal_print_format` y `Proposal Template.print_format`) desde el helper JS central
  `public/js/proposal_print_format.js` (incluido vía `app_include_js`).
- **Validación de servidor** `assert_assignable_print_format(doc, fieldname)` → corre en `validate` de
  Quotation y de Proposal Template. Es **change-aware**: bloquea que un documento nuevo/editable
  *adopte* un formato no elegible (API, import, script), pero **no** invalida una referencia previa no
  modificada — así un documento histórico/congelado que ya apuntaba a un formato luego deshabilitado
  **conserva** su referencia efectiva sin romperse.
- **Warning de referencia obsoleta** (`get_print_format_status`) → en `Proposal Template`, al cargar, si
  el `print_format` está `disabled` (obsoleto) o ya no existe / es de otro DocType, avisa junto al campo.

> Si mañana se agrega otra regla de elegibilidad, se cambia en `_proposal_print_format_filters` /
> `validate_print_format` y la heredan por igual la query, la validación y el warning. No se toca el
> selector estándar de impresión de Frappe.

---

## Archivos relevantes

| Archivo | Propósito |
|---|---|
| `propuesta_comercial.json` | Fuente de verdad del Print Format comercial genérico (default) |
| `utils/print_format_protection.py` | Candado de Print Formats históricos (ADR-0011) |
| `rentabilidad_estimada.json` | Fuente de verdad del Print Format de rentabilidad |
| `utils/print_format.py` | Resolución/congelamiento + selector central (`get_proposal_print_formats`), validación (`assert_assignable_print_format`), status (`get_print_format_status`), **render de portada separada + merge (`render_proposal_pdf`)** y **sincronización de Letter Head (`sync_letter_head_from_template`)** |
| `public/js/proposal_print_format.js` | Helper JS central: `set_query` + warning de obsoleto para ambos campos (`app_include_js`) |
| `utils/printing.py` | Helpers Jinja: `render_section_content`, `parse_json`, `get_sections_snapshot` (lectura fail-closed del snapshot), `get_logo_url`, `get_logo_data_uri`, **`keep_headings_with_next`**, **`section_number`**, **`service_item`** |
| `report/profitability_estimate/` | Fuente de datos para Rentabilidad Estimada |
| `working_docs/archive/visual-regression/` | PDFs de evidencia histórica por formato |
