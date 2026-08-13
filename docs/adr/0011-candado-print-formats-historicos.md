# ADR-0011: Candado de Print Formats históricos

**Fecha:** 2026-08-10 · **Actualizado:** 2026-08-12 (premisa de `disabled` revisada — ver *Actualización*)
**Status:** Cerrado — vigente (con actualización 2026-08-12)
**Rama:** feat/protect-historical-print-formats → version-16 · actualización en feat/print-format-versioning-selector

---

## Actualización 2026-08-12 — `disabled` deja de ser campo protegido

**Premisa que cambió:** originalmente se asumía que un Print Format histórico debía **permanecer
utilizable para reimpresión**, y por eso el candado incluía `disabled` entre los campos protegidos
(deshabilitarlo "rompería la reimpresión").

Esa premisa ya **no** es válida. Modelo definitivo:

- El **histórico oficial** de una propuesta congelada son los **PDFs oficiales adjuntos** generados en
  el freeze (protegidos contra borrado, ver `official_document_protection.py`). Una propuesta congelada
  **no se reimprime** normalmente; se consulta por esos PDFs.
- `proposal_effective_print_format` queda como **referencia/auditoría** del formato usado, **no** como
  mecanismo para re-renderizar el histórico.
- Por tanto `disabled` **no** forma parte de la representación histórica y **debe** poder pasar de
  `0 → 1` (por la vía normal `doc.save()`) al sustituir un formato por una versión nueva.

**Cambio concreto:** se **retira `disabled`** de `_PRESENTATION_FIELDS`. Siguen protegidos (inmutables
en históricos): `html`, `css` y demás campos de presentación, **rename** y **delete**. Sin bypass ni
escritura directa a BD: la corrección es en el propio guard. Recuperar un PDF oficial perdido pese a
las protecciones sería un procedimiento **extraordinario separado**, fuera del flujo normal.

---

## Contexto

Al congelar una propuesta (Borrador → En Revisión), el app persiste el **nombre** del Print Format
efectivo en `proposal_effective_print_format` (ver [ADR-0005](0005-resolucion-congelamiento-print-format.md)),
pero **no** congela el HTML/CSS del formato. La reimpresión de una propuesta ya emitida usa el HTML
**actual** del Print Format cuyo nombre quedó guardado. Por tanto, modificar, deshabilitar, renombrar
o eliminar un Print Format ya usado por propuestas congeladas **cambia retrospectivamente** su
presentación (o rompe la reimpresión). No existía ningún candado técnico que lo impidiera; solo el
rol System Manager podía editarlos, sin barrera condicional.

La estrategia de evolución ya validada es **versionar por nombre**: crear un Print Format nuevo y
apuntar a él solo las propuestas futuras (vía `Proposal Template.print_format`), dejando el histórico
intacto.

---

## Decisión

Se agrega un **candado técnico** dentro de `erpnext_proposals` (sin modificar Frappe core), mediante
`doc_events` estándar sobre el DocType **`Print Format`** (`utils/print_format_protection.py`):

- **Condición de "histórico":** `is_print_format_historical(name)` =
  `exists(Quotation, {proposal_effective_print_format: name})`. Ese campo se persiste **solo** al
  congelar, así que su presencia == el formato ya lo usa una propuesta formalizada.
- **Operaciones bloqueadas** cuando el formato es histórico:
  - **modificación** de campos que alteran la presentación/reimpresión (`html`, `css`, `format_data`,
    `print_format_type`, `custom_format`, `raw_printing`, `raw_commands`, márgenes, fuente,
    `page_number`, `pdf_generator`, `doc_type`, etc.) — hook `validate`;
  - **rename** — hook `before_rename`;
  - **delete** — hook `on_trash`.
- **Permitido explícitamente** (actualización 2026-08-12): cambiar **`disabled`** (típicamente
  `0 → 1`) aunque el formato sea histórico — no altera la representación histórica (los PDFs oficiales
  adjuntos son el histórico). Es la operación normal al versionar/sustituir un formato.
- **Idempotente:** el bloqueo de modificación solo dispara si algún campo protegido **realmente
  cambió** (`has_value_changed`). Re-guardar contenido idéntico (p. ej. el loader del pack
  re-aplicando el mismo formato) **no** se bloquea.
- **Sin excepción administrativa:** ni System Manager ni Administrator pueden modificar deliberadamente
  un formato histórico por el flujo normal. La corrección/evolución se hace **creando un formato nuevo
  con otro nombre**.
- **Genérico:** no hardcodea nombres de Print Formats.

---

## Consecuencias

- La reimpresión de propuestas históricas queda protegida contra alteración accidental o deliberada.
- Los formatos se evolucionan creando versiones nuevas por nombre; el histórico es inmutable.
- El loader del pack sigue siendo idempotente sobre formatos históricos (re-aplicar contenido idéntico
  no se bloquea; cambiar su contenido sí — lo cual es el comportamiento deseado: los formatos usados
  por propuestas formalizadas no deben cambiar).
- El candado corre en el guardado de **cualquier** Print Format del sistema, pero solo bloquea a los
  históricos (la verificación `exists` es un no-op para el resto).

---

## Alternativas descartadas

- **Snapshot del HTML por propuesta** (congelar el HTML dentro de la Quotation): resuelve la raíz pero
  cambia el modelo de datos del app; se prefirió el versionado por nombre + candado, de menor alcance.
- **Protección solo por roles/permisos:** es *coarse* (afecta todos los formatos) y no evita el
  accidente de quien sí tiene el permiso; sería disuasión humana, no un candado real.

---

## Fuera de alcance

- Endurecimiento adicional de roles/permisos (se mantienen los permisos actuales de Frappe).
- La lista estática `PROTECTED_PRINT_FORMATS` del loader (protege contra el loader, no contra edición
  manual) — es una capa distinta que se conserva.
