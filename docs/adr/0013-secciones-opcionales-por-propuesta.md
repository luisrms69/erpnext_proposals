# ADR-0013: Secciones narrativas opcionales activables por propuesta

**Fecha:** 2026-08-11
**Status:** Cerrado — vigente
**Rama:** feat/proposals-hardening → version-16

---

## Contexto

Algunas secciones del cuerpo de la propuesta solo aplican en casos puntuales — por ejemplo una
cláusula contractual de **sustitución de acuerdos anteriores** que solo tiene sentido cuando la nueva
propuesta reemplaza una relación contractual previa. Requisitos:

- **Opcional por propuesta:** no debe aparecer en todas las propuestas.
- **Activable/desactivable en una Quotation concreta**, sin duplicar Proposal Templates.
- **Reutilizable y genérica** (una Proposal Section del catálogo, no texto por cliente).
- **Congelada** dentro de la Quotation al formalizar, como el resto del cuerpo narrativo.
- **Sin Print Format especial.**

El modelo previo no lo permitía: `_build_sections_snapshot` incluía **todas** las filas del Template
(con Section `enabled` y contenido no vacío); el Check `include_by_default` de `Proposal Template
Section` existía pero estaba **inerte** (ningún código lo consumía); `hide_title` solo oculta el
heading, no la sección; y `proposal_sections_snapshot` es `read_only`+`hidden` (no editable a mano por
Quotation). No existía ningún interruptor de sección por Quotation.

---

## Decisión

Activar `include_by_default` como marca de sección **opcional** y agregar un selector por Quotation,
dentro de `erpnext_proposals` (sin tocar el Print Format ni duplicar Templates):

1. **Marca de opcionalidad (pack/config):** una fila de `Proposal Template Section` con
   **`include_by_default = 0`** declara la sección como opcional. El default sigue siendo `1`, por lo
   que **todas las secciones existentes conservan su comportamiento** (siempre entran).
2. **Selector por Quotation:** custom field **`proposal_optional_sections`** (Table MultiSelect →
   nuevo child DocType **`Proposal Optional Section`**, un Link a `Proposal Section`). Editable solo en
   Borrador (`read_only_depends_on: eval:doc.docstatus>0`). En la UI, el selector solo ofrece Proposal
   Sections habilitadas (`quotation.js` set_query).
3. **Builder:** `_build_sections_snapshot` construye el conjunto de Sections activadas desde
   `proposal_optional_sections` y **descarta las filas opcionales no seleccionadas**. Una selección que
   no corresponda a una fila opcional del Template asignado se **ignora** (no puede inyectar secciones
   ajenas). Las filas `include_by_default=1` entran igual que antes.
4. **Congelamiento:** la sección activada se serializa en `proposal_sections_snapshot` como cualquier
   otra entrada (hereda su `sequence` de la fila del Template; p. ej. `~640` para una cláusula legal de
   cierre antes del bloque de aceptación) y queda **inmutable** desde En Revisión. Cambiar el selector
   después de congelar **no** tiene efecto; en un Borrador ya poblado se refleja con *Sincronizar
   alcance desde catálogo* (resync, solo Borrador).

El **texto** de la cláusula (una Proposal Section del catálogo privado con `include_by_default=0` en
los Templates aplicables) se define por separado; esta ADR cubre la **capacidad**, no la redacción
jurídica definitiva.

---

## Consecuencias

- Se pueden ofrecer cláusulas/secciones opcionales por propuesta sin duplicar Templates ni tocar el
  Print Format. La activación es un check por Quotation, congelado en el snapshot.
- **Comportamiento retrocompatible:** como el default de `include_by_default` es `1` y todas las filas
  actuales lo tienen en `1`, ninguna propuesta existente cambia de contenido.
- La selección se **copia** al versionar (no `no_copy`), editable de nuevo en el Borrador de la nueva
  versión; el snapshot ya congelado se copia literal como siempre.

---

## Alternativas descartadas

- **Duplicar el Proposal Template** con/ sin la cláusula: multiplica Templates y viola el requisito.
- **`hide_title`** para "apagar" la sección: solo oculta el heading, no el cuerpo.
- **Editar el snapshot a mano por Quotation:** el campo es `read_only`+`hidden`; inviable en UI y
  frágil.
- **Section maestra por-template vía `custom_content`:** sigue siendo por Template, sin interruptor por
  propuesta.

---

## Fuera de alcance

- La **redacción jurídica definitiva** de la cláusula de sustitución de acuerdos (se aprueba y carga
  aparte, en el catálogo privado).
- Filtrar el selector a solo las filas opcionales del Template asignado (hoy ofrece Sections
  habilitadas y el builder ignora selecciones no aplicables). Mejora futura opcional.
