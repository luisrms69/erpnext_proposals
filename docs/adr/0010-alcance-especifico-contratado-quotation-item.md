# ADR-0010: Alcance específico contratado como campo manual por línea en `Quotation Item`

**Fecha:** 2026-08-10
**Status:** Cerrado — vigente
**Rama:** feat/scope-program-pmo-planning → version-16

---

## Contexto

El contenido editorial de cada servicio (descripción, metodología, resultado esperado, límite del
alcance) es **genérico**: describe el servicio en abstracto y viene del catálogo, congelado desde el
`Item` a cada `Quotation Item` (ver [ADR-0007](0007-contenido-editorial-item-y-congelamiento.md)).

Faltaba capturar el **alcance concreto de cada contratación**: qué se contrató exactamente en esta
propuesta para ese servicio (número de compañías, usuarios, entregables acotados, meses de
acompañamiento, etc.). Ese dato es **específico de la propuesta**, no del catálogo, lo escribe la
persona que arma la propuesta y debe quedar **congelado y auditable** junto con el resto del contenido
al someter.

---

## Decisión

Se agrega **un** custom field `proposal_specific_scope` (Text Editor) en `Quotation Item`, con estas
propiedades:

- **Entrada manual, editable en Borrador** (`read_only=0`, `hidden=0`): la persona lo captura en la
  fila expandida de cada servicio. `reqd=0` (opcional), `allow_on_submit=0`, `print_hide=1`.
- **No proviene del catálogo ni del `Item`.** Queda **fuera** de `_FROZEN_ITEM_FIELDS` (la copia
  `Item → Quotation Item`) y **fuera** de `_CATALOG_CONTROLLED_FIELDS` (los campos de `Quotation Scope
  Item` que el resync refresca). Por eso **el resync del alcance no lo toca** — un *Regenerar alcance*
  conserva lo escrito.
- **Se congela al someter** usando los mecanismos existentes, sin freeze paralelo: `allow_on_submit=0`
  (núcleo de Frappe) más el hook `on_quotation_before_update_after_submit`, que ya rechaza cualquier
  edición post-submit fuera de las transiciones de workflow.
- **Se hereda al versionar:** `create_new_proposal_version` lo copia en `_copy_item(...)`, quedando
  editable de nuevo en el Borrador de la nueva versión sin alterar la anterior.
- **Independiente por línea:** el mismo `Item` repetido en dos líneas puede tener alcances distintos.

El Print Format que lo consume (en el pack privado) lo lee **exclusivamente** desde
`Quotation Item.proposal_specific_scope` y **solo lo imprime si tiene contenido**; nunca relee
`Item`/catálogo/Scope Item en runtime.

---

## Consecuencias

- El alcance contratado de cada servicio queda capturado, congelado y auditable con las mismas
  garantías que el resto del contenido de la propuesta, reutilizando el congelamiento existente.
- El resync desde catálogo y el congelamiento editorial `Item → Quotation Item` **no cambian**: el
  campo vive fuera de ambos conjuntos, así que no hay riesgo de que se pise o se pierda.
- El congelamiento es **control de proceso**, no inmutabilidad criptográfica: una escritura directa a
  BD (`frappe.db.set_value`/SQL) evade `allow_on_submit` y el hook, igual que el resto de campos.

---

## Alternativas descartadas

- **Nuevo DocType hijo para el alcance contratado:** sobredimensionado para un texto por línea;
  duplicaría el ciclo de congelamiento ya resuelto en `Quotation Item`.
- **Reusar/extender el contenido editorial del `Item` o del catálogo:** el alcance contratado es
  específico de cada propuesta, no genérico; meterlo en el catálogo rompería la separación de
  [ADR-0007](0007-contenido-editorial-item-y-congelamiento.md) y lo haría releer maestros.
- **Incluirlo en `_FROZEN_ITEM_FIELDS`:** el resync lo sobrescribiría con el (inexistente) valor del
  `Item`, borrando lo escrito.

---

## Fuera de alcance

- El diseño del Print Format que lo renderiza (vive en el pack privado — ver
  [ADR-0006](0006-separacion-app-generica-personalizacion-privada.md)).
- Un diálogo JS de captura enriquecida: por ahora la captura es en la fila expandida nativa.
