# ADR-0004: `phase` como Link a Proposal Phase

**Fecha:** 2026-07-15
**Status:** Cerrado — implementado (rama `feat/proposal-phase-link`)
**Rama:** feature/proposal-phase-link → version-16

---

## Contexto

El campo `phase` en `Scope Item` y `Quotation Scope Item` era **texto libre** (`Data`), lo que
producía valores inconsistentes ("Fase 1", "Fase 1 — Análisis", "Análisis"…) y un orden
**alfabético** incorrecto (el código `DISC/IMPL/GOLIVE` ordena alfabéticamente distinto a su
secuencia real). El catálogo `Proposal Phase` (ADR previo / PR #26) existía pero no estaba
conectado.

---

## Decisión

- `Scope Item.phase` y `Quotation Scope Item.phase` → **Link a `Proposal Phase`** (almacena el
  `name` = `phase_code`).
- **El orden** en propuesta, Rentabilidad Estimada y Tasks del proyecto se resuelve por
  **`Proposal Phase.sequence`** (no alfabético). El **display** usa `phase_name` legible.
- **No se duplica `sequence`/`phase_name`** en los DocTypes: se resuelven desde el catálogo en
  tiempo de lectura mediante `utils/phase.py` (`phase_label`, `phase_sequence`, `order_phases`;
  `phase_label` y `order_phases` registrados como jinja methods para los Print Formats).
- La sincronización de alcance (ADR-0003) sigue copiando `phase` como campo controlado por catálogo.
- **Corte limpio, sin migración de datos históricos:** no se implementa patch, backfill ni
  compatibilidad con valores libres. Cada sitio configura su catálogo `Proposal Phase` antes de
  capturar Scope Items y propuestas. Los datos de dev/prueba se ajustan manualmente.

---

## Consecuencias

- Un `Scope Item` sin fase sigue funcionando (campo opcional); un valor inexistente es rechazado
  por la validación del Link.
- Consumidores actualizados: generación de scope, resync, versionado, creación de proyecto,
  Rentabilidad Estimada y ambos Print Formats.
- **Despliegue:** requiere `bench migrate` (aplica el cambio de fieldtype) y recargar los Print
  Formats (`reload_doc … force=True`); regenerar assets por el cambio de JS/Jinja no aplica aquí,
  pero sí el reload de Print Formats. Los datos históricos con valores libres quedan como Links
  inválidos hasta que se ajusten manualmente (decisión explícita).

---

## Alternativas descartadas

- **Campo `phase_sequence` almacenado** en los DocTypes como fuente de orden: descartado para no
  duplicar la fuente de verdad; el orden se resuelve desde `Proposal Phase.sequence`.
- **Backfill/patch de datos históricos**: descartado — los sitios objetivo son implementaciones
  nuevas; los datos actuales son de prueba y se ajustan manualmente.

---

## Fuera de alcance

- Nuevas funcionalidades del re-sync, `manual_override`, costos, workflow, templates o Project.
