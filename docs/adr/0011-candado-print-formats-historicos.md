# ADR-0011: Candado de Print Formats históricos

**Fecha:** 2026-08-10
**Status:** Cerrado — vigente
**Rama:** feat/protect-historical-print-formats → version-16

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
  - **`disabled`** (deshabilitar rompe la reimpresión) — hook `validate`;
  - **rename** — hook `before_rename`;
  - **delete** — hook `on_trash`.
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
