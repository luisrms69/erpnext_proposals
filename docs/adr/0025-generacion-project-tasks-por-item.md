# ADR-0025: Generación de Project/Tasks por Item (Proposal Phase deja de agrupar y de ser obligatoria)

**Fecha:** 2026-10-06
**Status:** Cerrado — vigente. Modelo de materialización Quotation Ganada → Project/Tasks.
**Rama:** feat/project-item-parent → version-16

---

## Contexto

El modelo anterior ([ADR-0004](0004-phase-link-proposal-phase.md)) agrupaba las Tasks del Project por
**Proposal Phase**: una Task-fase padre (`is_group=1`, campo `proposal_phase`) por fase, con las Tasks de
Scope como hijas. Esto imponía tres costos:

1. **Fase obligatoria.** El preflight exigía que *toda* fila ejecutable tuviera fase; una actividad sin
   fase bloqueaba la creación del Project (y la transición a «Ganada»).
2. **Propuestas de solo licenciamiento sin programa.** Un Item vendido sin Scope propio solo generaba Task
   si existía el fallback de **compromiso** (`default_commitment_scope_item`) configurado. Sin él, ganar
   una propuesta de solo licencias Microsoft **no generaba tareas** (y `assert_program_prerequisites`
   incluso bloqueaba la transición a «Ganada»).
3. **Scope artificial.** El compromiso materializaba un Scope Item de relleno por ocurrencia, una segunda
   fuente de verdad para “representar la entrega”.

La agrupación por fase, además, no la consume nada funcional: `Task.proposal_phase` no se lee en costos,
programación, dependencias ni en el app `pmo` (que trata el árbol de Tasks de forma genérica:
`is_group`/`parent_task`/hoja). El color y los Tags de fase en la Task padre eran solo cosméticos.

## Decisión

La materialización pasa a un modelo **por Item contratado**, con el **mismo criterio** en la creación del
Project raíz y en la aplicación de addendas ([ADR-0019](0019-aplicar-addendum-a-project-existente.md)):

1. **Cada ocurrencia de Item vendido → una Task padre** (`is_group=1`). Sus Scope Items ejecutables son
   las Tasks hijas. Si la ocurrencia vendida **no tiene alcance ejecutable**, se genera **una Task
   operativa inicial** (`is_group=0`, subject `"Entregar — <item>"`), **sin crear Scope Items artificiales**.
2. **Required Items** generan Task padre **solo** cuando representan una obligación operativa real (≥1
   QSI: alcance propio o compra aplicable). Los insumos internos (paquete de compras, `proposal_skip_procurement`)
   no generan padre.
3. **Proposal Phase deja de ser obligatoria y de generar Tasks padre.** Sobrevive como **etiqueta y orden
   de presentación** (sigue siendo Link válido en Scope Item / Quotation Scope Item; ADR-0004 se ajusta en
   esto). Se retira el snapshot de color/Tags de fase en las Tasks padre.
4. **Se retira `default_commitment_scope_item`** (campo del DocType Proposal Settings + su generación +
   su prerrequisito en `assert_program_prerequisites`). La Task operativa lo vuelve redundante. La columna
   huérfana queda NULL y **no se borra por SQL** (sin pérdida de datos; sin patch).
5. **Idempotencia por ocurrencia:** nuevo Custom Field `Task.source_quotation_item_row` (= `name` del
   Quotation Item / Proposal Required Item de origen). Clave del padre `(project, source_quotation_item_row,
   is_group=1)`; de la Task operativa `(…, is_group=0)`; de las hijas de scope `(project,
   source_quotation_scope_item)`. Reejecutar o reaplicar la misma addenda no duplica.
6. **Addendas (criterio idéntico):** una addenda que aporta **trabajo nuevo** (Item vendido o scope
   ejecutable) materializa padre + Task operativa/scope; una addenda **exclusivamente económica** (sin
   Items vendidos: solo Required / delta $0 / contractual) aplica con **0 Tasks**. Seguro porque la addenda
   es DELTA (no re-enuncia el alcance de la raíz → sin padres duplicados).
7. **Presentación (PDF Propuesta Comercial y report Rentabilidad):** agrupan por **fase cuando todas** las
   filas tienen fase (comportamiento previo, sin cambio visual); si **falta** alguna, agrupan por **Item**.
   Nunca modo mixto.

**No cambia:** la regla de **compras** (`default_purchase_scope_item`, fallback de compra por obligación)
ni el **Control de Cambios** (ADR-0019): su contrato económico, idempotencia y atomicidad se conservan.

## Consecuencias

- Una propuesta (o addenda) de **solo licenciamiento** genera Project + Task operativa por Item, sin
  configuración especial.
- **PMO** amplía libremente el árbol bajo cada Task-Item; su identidad (`source_quotation_item_row`,
  read-only) sobrevive a cualquier edición que no borre la Task.
- **Proyectos históricos no se migran** ([decisión de alcance]): un Project creado con Tasks-fase que
  reciba una addenda post-cambio tendrá coexistencia temporal de padres-fase (viejos) y padres-Item
  (nuevos). No duplica ni bloquea; PMO lo lee igual.
- Sin **patch** (quitar un campo + añadir un Custom Field no migra datos). Instalación nueva por
  `install-app` y actualización por `bench migrate`, sin intervención manual.

## Relación con otros ADR

- Ajusta **ADR-0004** (Proposal Phase como Link): la fase deja de ser obligatoria y de agrupar Tasks;
  permanece como Link de etiqueta/orden.
- Compatible con **ADR-0017** (Required Items aditivo) y **ADR-0019** (addenda apply-split): la addenda
  reusa el mismo materializador, ahora por Item.
