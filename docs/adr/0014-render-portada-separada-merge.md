# ADR-0014: Render de portada separada + merge con pypdf

**Fecha:** 2026-08-26
**Status:** Cerrado — vigente
**Rama:** feat/proposal-rendering-infrastructure → version-16

---

## Contexto

El PDF comercial de una familia de propuesta necesita, a la vez, dos cosas **incompatibles en una
sola pasada de render**:

- Una **portada full-bleed a sangre** (imagen/branding que ocupa toda la página, sin márgenes).
- Un **encabezado de marca (Letter Head) repetido en todas las páginas del cuerpo** más un footer de
  cierre.

Un encabezado corrido (header repetido de wkhtmltopdf) exige un **margen superior uniforme** en todo
el documento. Ese margen deja una **franja blanca** arriba de cada página — incluida la portada — que
choca directamente con una portada a sangre. No se puede tener margen superior cero para la portada y
margen superior positivo para el cuerpo en el mismo render.

Además, en un Print Format custom el header declarado por CSS/Jinja **cae fuera del área de página**
(no lo repite el motor de forma fiable), por lo que el patrón nativo de `#header-html` de Frappe no
resuelve el caso.

---

## Decisión

Cuando la `Proposal Template` marca **`separate_cover_page = 1`** y se renderiza su Print Format
comercial, el PDF se produce en **dos renders unidos con el merger PDF nativo de Frappe (pypdf)**, sin
rasterizar y sin postproceso externo. La orquestación vive en `render_proposal_pdf(doc, print_format)`
(`utils/print_format.py`), cableada desde `utils/quotation.py::_attach_pdf`:

1. **Render 1 — portada:** solo la portada, **sin Letter Head** (`no_letterhead`), margen superior
   cero. Se toma **solo la primera página** del resultado.
2. **Render 2 — cuerpo:** todo el cuerpo con el **Letter Head repetido como encabezado en todas las
   páginas** + footer.
3. **Merge:** ambos PDFs se concatenan con **pypdf** (merger nativo de Frappe), preservando el vector
   (no se rasteriza).

El **modo de render** se pasa por un atributo del propio `doc` — **`doc.proposal_render_part`**
(`'cover'` | `'body'`) — que **solo el Print Format consume** para decidir qué bloque emitir y si lleva
Letter Head. **No** hay monkey-patch a `get_pdf`, **no** se toca Frappe core, y **no** se afecta a
ningún otro Print Format.

**Fallback backward-compatible:** cualquier plantilla **sin** la marca `separate_cover_page`, o
**cualquier otro Print Format** (p. ej. `Rentabilidad Estimada`), usa **un solo render** con el
comportamiento estándar de siempre. La ruta de dos renders solo se activa con la marca **y** el Print
Format comercial de esa plantilla.

El Letter Head del cuerpo se elige de forma **explícita por nombre** vía
`Proposal Template.letter_head` → `Quotation.letter_head` (ver ADR-0006 sobre datos genéricos y
`tecnico/print-formats.md`), independiente del default del sitio.

---

## Consecuencias

- Se concilia una portada full-bleed a sangre con un encabezado de marca repetido en el cuerpo, algo
  imposible en un solo render.
- El resultado es **determinista**: el merge con pypdf no depende de herramientas externas ni de un
  paso de rasterizado, y conserva el PDF vectorial.
- El acoplamiento con el Print Format es mínimo y **opt-in**: solo un atributo efímero en el `doc`
  (`proposal_render_part`); sin este atributo o sin la marca, el comportamiento es idéntico al previo.
- **No** se toca Frappe core ni el resto de Print Formats. `Rentabilidad Estimada` y cualquier formato
  sin la marca siguen en un único render.
- Relacionado con [ADR-0005](0005-resolucion-congelamiento-print-format.md) (resolución/congelamiento
  del Print Format comercial) y [ADR-0006](0006-separacion-app-generica-personalizacion-privada.md)
  (el mecanismo es genérico; los Letter Heads/branding concretos viven en el catálogo privado).

---

## Alternativas descartadas

- **Single-render con `#header-html` repetible (patrón nativo de Frappe):** en un Print Format custom
  el header cae **fuera del área de página** y no se repite de forma fiable; además el margen superior
  uniforme que exige el header choca con la portada full-bleed a sangre. Descartado.
- **`position: fixed` para repetir el encabezado en cada página:** wkhtmltopdf **no** lo repite de
  forma fiable página a página. Descartado.
- **Dos renders + merge con pypdf (elegido):** separar portada (sin Letter Head, margen cero) y cuerpo
  (con Letter Head repetido) y unirlos con el merger nativo reconcilia ambos requisitos sin tocar core.

---

## Fuera de alcance

- El **diseño visual concreto** de la portada y del Letter Head de cada cliente (viven en el catálogo
  privado; el app solo aporta el mecanismo genérico — ver ADR-0006).
- Repetir un header corrido de wkhtmltopdf sin merge: no resuelve la portada a sangre (ver
  alternativas descartadas).
