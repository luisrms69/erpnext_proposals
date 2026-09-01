# SOW (Statement of Work)

El **SOW** es un **tercer documento oficial** de la propuesta, orientado a la ejecución del proyecto.
No es un mecanismo aparte: es **otra representación del mismo contenido** de la Quotation, con el mismo
sistema de generación que la propuesta comercial (mismo renderer, mismo congelamiento, misma protección
histórica). Solo cambia el Print Format.

## Cómo se activa

En la **Proposal Template** de la propuesta, el campo **`SOW Print Format`** (`sow_print_format`) define
el formato del SOW para esa familia de propuesta:

- **Vacío** → no se genera SOW (la propuesta funciona igual que siempre).
- **Con un Print Format** → el SOW queda disponible como documento adicional.

El SOW usa el **mismo contenido congelado** que la propuesta comercial (Items, Scope Items, fases,
metodología, resultado esperado, límite de alcance, datos de cliente/proyecto y snapshot de secciones).

## Acciones en la Quotation (grupo *Propuesta*)

En **Borrador**, para revisión mientras la propuesta sigue editable:

| Botón | Qué hace |
|---|---|
| **Vista previa comercial** | Abre el HTML de la propuesta comercial |
| **Descargar PDF comercial** | Descarga el PDF (borrador) de la propuesta comercial |
| **Vista previa rentabilidad** | Abre el HTML de la Rentabilidad Estimada |
| **Descargar PDF rentabilidad** | Descarga el PDF (borrador) de la Rentabilidad Estimada |
| **Vista previa SOW** | Abre el HTML del SOW |
| **Descargar PDF SOW** | Descarga el PDF (borrador) del SOW |

Las descargas en Borrador llevan el prefijo **BORRADOR** y **no** son el documento oficial.

## Generación automática al pasar a *En Revisión*

Al mover la Quotation de **Borrador → En Revisión**, el sistema **congela** el contenido y genera y
**adjunta automáticamente** los **tres documentos oficiales**, todos **privados e inmutables**:

1. Propuesta comercial
2. Rentabilidad (valuación económica)
3. **SOW**

Estos PDFs quedan adjuntos a la misma Quotation, se descargan después desde ahí y **no cambian** aunque
después se modifique el catálogo, los Scope Items, los Items, las fases o las plantillas (protección
histórica; ver [ADR-0012](../adr/0012-proteccion-eliminacion-pdfs-oficiales.md)). El SOW solo se genera
si la plantilla define `sow_print_format`.

## Diseño

El SOW reutiliza el mismo tratamiento visual que la propuesta comercial (misma portada separada, header,
footer y márgenes). La **portada separada** se controla con la misma opción **`separate_cover_page`** de
la plantilla, que ahora aplica por igual a la propuesta comercial y al SOW.
