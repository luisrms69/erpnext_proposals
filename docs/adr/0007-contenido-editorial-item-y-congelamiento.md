# ADR-0007: Contenido editorial del servicio en `Item` y congelamiento inmutable en la Quotation

**Fecha:** 2026-07-29
**Status:** Cerrado — vigente
**Rama:** chore/gitignore-local-artifacts → version-16

---

## Contexto

El contenido comercial de una propuesta tiene dos partes:

1. **Contenido del servicio** (descripción, metodología, resultado esperado, límite del alcance) —
   propio de cada servicio ofrecido.
2. **Cuerpo narrativo** (introducción, quiénes somos, condiciones, confidencialidad, vigencia) —
   Proposal Sections del Template.

Antes, el contenido editorial del servicio se guardaba en `Scope Item` (el catálogo de actividades).
Eso mezclaba dos conceptos distintos: **qué actividad se ejecuta** (Scope Item: perfil, horas, fase)
vs **cómo se describe comercialmente el servicio** (contenido editorial). Además, tanto el contenido
del servicio como el cuerpo narrativo se releían de los maestros al imprimir, de modo que un cambio
posterior en el catálogo alteraba propuestas ya enviadas y PDFs históricos.

---

## Decisión

### 1. El contenido editorial del servicio vive en el `Item`, no en `Scope Item`

Se agregan custom fields al `Item` (administrados por el catálogo): `proposal_content_section`,
`proposal_methodology`, `proposal_expected_result`, `proposal_scope_limit` (más el `description`
nativo). El `Scope Item` conserva **solo** actividad, perfil, horas estimadas y fase.

### 2. El contenido se **congela** dentro de la Quotation

- **Contenido del servicio:** al generar el alcance, `_copy_item_proposal_fields` copia
  `description` + los tres `proposal_*` del `Item` a cada línea nativa `Quotation Item`
  (`_FROZEN_ITEM_FIELDS`). Solo congela líneas nuevas en la generación inicial; el resync explícito
  (`force=True`, solo en Borrador) refresca todas.
- **Cuerpo narrativo:** las Proposal Sections del Template se capturan en
  `Quotation.proposal_sections_snapshot` (JSON) mediante `_sync_sections_snapshot` /
  `_build_sections_snapshot`, **solo si está vacío** (generación inicial) o vía resync (`force=True`).

### 3. El Print Format lee **siempre** la copia congelada

El PDF comercial usa `Quotation Item` y `proposal_sections_snapshot`, **nunca** relee los maestros
(`Item`, `Proposal Section`, `Proposal Template`). La lectura del snapshot es **fail-closed**
(`utils/printing.py::get_sections_snapshot`): si está ausente, vacío o inválido, el formato muestra
solo una advertencia de no entrega y no renderiza alcance/inversión/firma.

### 4. Inmutabilidad tras el freeze

El snapshot se **conserva** al pasar a *En Revision* (inmutable desde ahí) y se copia **literalmente**
al versionar (mismo contenido/orden/`captured_on`). La única vía de actualizarlo es el **resync**,
y solo mientras la propuesta siga en Borrador.

---

## Consecuencias

- Separación limpia: `Scope Item` = actividad/costo; `Item` = contenido comercial del servicio.
- Las propuestas enviadas y los PDFs históricos **no cambian** aunque el catálogo evolucione.
- El catálogo (loader) administra el contenido editorial del `Item` de forma idempotente.
- `hide_title` (por `Proposal Template Section`) también se congela por entrada del snapshot, de modo
  que ocultar/mostrar un heading en un Template no altera PDFs previos.

---

## Alternativas descartadas

- **Mantener el contenido editorial en `Scope Item`:** mezcla actividad con narrativa del servicio y
  obliga a duplicar contenido cuando varios Scope Items pertenecen al mismo servicio/Item.
- **Releer maestros al imprimir:** rompe la inmutabilidad — un cambio de catálogo alteraría propuestas
  ya enviadas.

---

## Fuera de alcance

- El contenido editorial concreto de cada cliente (vive en su catálogo privado — ver
  [ADR-0006](0006-separacion-app-generica-personalizacion-privada.md)).
- El diseño del Print Format comercial (ver
  [ADR-0005](0005-resolucion-congelamiento-print-format.md)).
