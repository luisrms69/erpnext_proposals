# ADR-0022: Narrativa materializada en la Quotation (Master/Template → Draft autosuficiente)

**Fecha:** 2026-09-21 · **Status:** Cerrado — vigente
**Rama:** feat/quotation-sections-child-table → version-16

---

## Contexto

La narrativa de la propuesta (las Sections del cuerpo) vivía como un JSON congelado
(`proposal_sections_snapshot`) que se construía leyendo en vivo los maestros (Proposal Template +
Proposal Section) y se sincronizaba en varios puntos (generación, resync, freeze). Ese mecanismo era
una capa paralela al patrón nativo de ERPNext (documento que copia del maestro una vez y luego es
autosuficiente), y obligaba a mantener sincronización, validación fail-closed de JSON y un segundo
congelamiento explícito además del `docstatus`.

## Decisión

La narrativa sigue el patrón nativo Master/Template → transacción:

- **Materialización en Draft:** al generar la propuesta en Borrador (con Template asignado y la tabla
  vacía), las Sections **efectivas** del Proposal Template + Proposal Section se copian a la child
  table `proposal_sections` de la Quotation (DocType `Proposal Quotation Section`: `sequence`,
  `proposal_section`, `hide_title`, `is_executive_summary`, `title`, `content`).
- **Draft independiente:** desde ese momento las filas son datos propios de la Quotation. Cambios
  posteriores en Proposal Template o Proposal Section **no se propagan** automáticamente.
- **Reaplicación explícita:** la única forma de reponer la composición desde los maestros es la acción
  explícita de resync (reemplaza por completo las filas). Sin merge, diff ni preservación selectiva.
- **Inmutabilidad por `docstatus`:** al pasar a En Revisión/Submit (`docstatus=1`), las filas quedan
  inmutables por Frappe. No hay snapshot narrativo ni segundo mecanismo de freeze.
- **Rendering:** los Print Formats (incluidos los privados del pack) leen exclusivamente
  `proposal_sections`; el HTML no cambió.
- **PDF oficial = evidencia histórica:** el PDF adjunto en la formalización es la reproducción histórica
  de la propuesta.

`proposal_sections_snapshot` **permanece en el esquema** únicamente como **compatibilidad histórica**:
se lee para renderizar documentos antiguos que aún lo tienen, y se convierte **una sola vez** a
`proposal_sections` cuando se crea una nueva versión desde una propuesta legacy que solo tiene el
snapshot. No se escribe en el flujo nuevo.

## Consecuencias

- Se elimina la sincronización automática con maestros y el segundo freeze narrativo; el congelamiento
  narrativo es `docstatus`.
- El versionado hereda `proposal_sections` como child table normal (copia literal), no el JSON.
- Quedan sin uso (legacy, aún presentes) `_sync_sections_snapshot` / `_build_sections_snapshot` y el
  campo `proposal_sections_snapshot` (lectura de históricos + conversión). Su borrado físico es una
  fase posterior.
- El congelamiento **económico** (rates/costs/economic_behavior por *locks* +
  `assert_economic_snapshot_complete`) **no** se toca en esta decisión; su alineación con `docstatus`
  es trabajo posterior.

### Alternativa descartada

Mantener el `proposal_sections_snapshot` como fuente narrativa (con sincronización + validación JSON +
freeze explícito) en paralelo al `docstatus`. Se descarta por duplicar el patrón nativo y sostener una
capa de compensación innecesaria.
