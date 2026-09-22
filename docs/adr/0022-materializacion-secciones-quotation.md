# ADR-0022: Materialización en la Quotation (Master/Template → Draft autosuficiente → docstatus inmutable)

**Fecha:** 2026-09-21 · **Actualizado:** 2026-09-22 (extendido a economía, Print Format comercial y SOW; B1–B9)
**Status:** Cerrado — vigente. **Modelo canónico de materialización** de la propuesta.
**Rama:** feat/quotation-sections-child-table → version-16

**Enmienda / supersede parcial:** este ADR es la decisión canónica que reemplaza el mecanismo de
*freeze/snapshot/locks* descrito (para su época, correctamente) en
[ADR-0005](0005-resolucion-congelamiento-print-format.md) (congelamiento de Print Format),
[ADR-0007](0007-contenido-editorial-item-y-congelamiento.md) (snapshot narrativo `proposal_sections_snapshot`),
[ADR-0017](0017-required-items-modelo-economico-aditivo.md) y
[ADR-0018](0018-evaluacion-economica-por-periodos.md) (snapshot económico + locks al freeze) y ajusta la
herencia económica de [ADR-0021](0021-versionado-inherit-by-default.md). [ADR-0011](0011-candado-print-formats-historicos.md)
sigue vigente, con su detección de "histórico" ampliada al campo materializado. Esos ADR conservan su
valor histórico; el mecanismo vigente es el de aquí.

---

## Contexto

La propuesta congelaba su estado en el paso Borrador → En Revisión con una capa paralela al patrón
nativo de ERPNext (documento que copia del maestro una vez y luego es autosuficiente):

- **Narrativa:** JSON `proposal_sections_snapshot` construido leyendo maestros en vivo y sincronizado en
  varios puntos (`_sync_sections_snapshot`/`_build_sections_snapshot`).
- **Economía:** tarifa laboral, costo externo y comportamiento económico se resolvían **en el freeze** y
  se marcaban con *locks* (`rate_locked`/`rate_locked_on`, `proposal_cost_locked`, `cost_locked`).
- **Print Format:** el formato comercial efectivo se persistía en `proposal_effective_print_format` al
  freeze; el SOW se resolvía **en vivo** desde el Template incluso para propuestas ya formalizadas.

Eso obligaba a mantener sincronización, validación fail-closed de JSON, *locks* y un segundo mecanismo de
congelamiento además del `docstatus`, y dejaba lecturas "vivas" contra maestros en documentos ya formales.

## Decisión

Todo el estado de la propuesta sigue el patrón nativo **Master/Template → materialización en Draft →
Draft autosuficiente → `docstatus=1` inmutable**:

1. **Materialización en Draft (generación):** con Template asignado, en Borrador se copian a la Quotation
   los valores **efectivos**:
   - **Narrativa** → child table `proposal_sections` (`Proposal Quotation Section`: `sequence`,
     `proposal_section`, `hide_title`, `is_executive_summary`, `title`, `content`).
   - **Economía** → `costing_rate`/`rate_source` (Scope Item, desde Proposal Cost Matrix), costo externo
     `proposal_frozen_cost_rate`/`_source` (Item vendido) y `frozen_cost_rate`/`_source` (Required Item,
     pricing nativo), y comportamiento económico `proposal_economic_behavior`/`billing_interval`/`count`
     (Item y Required, desde Proposal Settings de la Company).
   - **Print Format comercial** → `proposal_print_format` (campo normal; override→Template→DEFAULT elegible).
   - **SOW Print Format** → `proposal_sow_print_format` (campo normal; desde `Proposal Template.sow_print_format`).
2. **Draft autosuficiente:** desde la materialización, los valores son datos propios de la Quotation.
   Cambios posteriores en Proposal Template, Proposal Section, Cost Matrix, Item pricing o Proposal
   Settings **no se propagan** automáticamente.
3. **Reaplicación explícita:** la única vía de refrescar desde los maestros es el **resync** en Borrador
   (reemplaza por completo narrativa y economía; reaplica los PF). Sin merge, diff ni preservación
   selectiva.
4. **Inmutabilidad por `docstatus`:** al pasar a En Revisión/Submit (`docstatus=1`), Frappe congela filas
   y campos. **No** hay snapshot narrativo, ni *locks*, ni `proposal_effective_print_format`, ni un
   segundo freeze: el `docstatus` es la única inmutabilidad.
5. **Ningún documento formal nuevo relee masters vivos:** los lectores (rendering, Rentabilidad Estimada,
   Evaluación Económica, resolución de Print Format y SOW) usan **exclusivamente** los valores
   materializados en la Quotation cuando `docstatus=1`. Si un documento formal nuevo careciera de un valor
   materializado, la lectura económica **falla-cerrada** (lanza), nunca cae en silencio a un master vivo.
6. **PDF oficial = evidencia histórica:** el PDF adjunto en la formalización es la reproducción histórica.

`freeze_proposal()` quedó **inerte y se eliminó**; el gate de formalización (`on_quotation_before_submit`)
solo exige que la economía esté materializada (`assert_economic_snapshot_complete`, verificando los
**valores** `*_source`/behavior, no los *locks*).

### Versionado (ajuste sobre ADR-0021)

Una nueva versión **hereda** los valores materializados (narrativa como child table; economía y PF como
campos/valores) → el nuevo Draft es autosuficiente. Ya **no** se "re-congela" la economía en la
formalización; para traer valores vigentes se usa el **resync explícito**. Se heredan los valores, no los
*flags* de lock (que no se usan en el flujo nuevo).

## Consecuencias

- Se elimina la sincronización automática con maestros y el segundo freeze (narrativo, económico y de PF).
- Runtime retirado: `freeze_proposal`, `freeze_effective_print_format`, `_sync_sections_snapshot`,
  `_build_sections_snapshot` y los fallbacks "vivos" en documentos formales (ahora fail-closed).
- **Compatibilidad legacy conservada** (solo lectura/entrada, no se escribe en el flujo nuevo):
  - `proposal_sections_snapshot`: lectura para renderizar propuestas históricas + conversión **única**
    a `proposal_sections` al versionar una Rechazada legacy (`_convert_legacy_snapshot_to_rows`).
  - `proposal_effective_print_format`: resolución del PF comercial y del SOW para submitted **anteriores**
    a la materialización (única fuente para reproducir su formato).
- **Campos legacy** (`rate_locked`, `rate_locked_on`, `proposal_cost_locked`, `cost_locked`,
  `proposal_sections_snapshot`, `proposal_effective_print_format`) permanecen en el esquema; su borrado
  físico es una fase posterior, una vez confirmado que ningún consumidor funcional los requiere.

### Alternativa descartada

Mantener el snapshot/lock/effective como fuente en paralelo al `docstatus`. Se descarta por duplicar el
patrón nativo, sostener capas de compensación y permitir lecturas vivas en documentos ya formales.
