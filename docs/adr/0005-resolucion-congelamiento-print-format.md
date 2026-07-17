# ADR-0005: Resolución y congelamiento del Print Format comercial

**Fecha:** 2026-07-17
**Status:** Cerrado — implementado
**Rama:** feat/proposal-project-task-integration → version-16

---

## Contexto

El app necesitaba que distintas propuestas usaran distintos Print Formats comerciales (por tipo
de proyecto / familia) sin crear sistemas paralelos, y garantizar que una propuesta ya emitida
**no cambie de formato** aunque después se editen los defaults. Antes existía un único formato
`Propuesta Comercial` fijo.

---

## Decisión

**Cadena de resolución** (módulo `utils/print_format.py`), de mayor a menor precedencia:

1. **Override por Quotation** — `proposal_print_format` (Link a Print Format, editable en Borrador).
2. **Default por Proposal Template** — `Proposal Template.print_format`.
3. **Default del app** — `DEFAULT_COMMERCIAL_PRINT_FORMAT = "Propuesta Comercial"` (genérico).

**Congelamiento:** al pasar Borrador → *En Revisión*, `freeze_effective_print_format(doc)` persiste
el formato resuelto en `proposal_effective_print_format` (read-only, `no_copy`, inmutable). A partir
de ahí `resolve_commercial_print_format(doc)` devuelve siempre el congelado. Una **nueva versión**
hereda ese formato como override editable.

- Un único resolver alimenta el botón de impresión (JS, vía `get_effective_commercial_print_format`
  whitelisted), el snapshot de impresión y el PDF adjunto → todos los caminos coinciden.
- `validate_print_format` rechaza formatos inexistentes, de otro `doc_type` o deshabilitados.

---

## Consecuencias

- El formato efectivo de una propuesta congelada es estable y auditable (`proposal_effective_print_format`).
- Los templates pueden fijar su formato por familia sin tocar código; una propuesta puede sobreescribirlo
  puntualmente en Borrador.
- **Despliegue:** requiere `bench migrate` (custom fields `proposal_print_format`,
  `proposal_effective_print_format`, `Proposal Template.print_format`) y recargar los Print Formats.

---

## Alternativas descartadas

- **Un único Print Format fijo:** no permitía variar por familia ni por propuesta.
- **Resolver en cada impresión sin congelar:** una propuesta emitida podría cambiar de formato al
  editar defaults — inaceptable para un documento ya presentado.

---

## Fuera de alcance

- El diseño visual de formatos branded específicos de cliente (dato privado, fuera del repo —
  ver [ADR-0006](0006-separacion-app-generica-personalizacion-privada.md)).
