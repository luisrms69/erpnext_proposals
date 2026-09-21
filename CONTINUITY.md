# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-20
**Rama activa:** `fix/commercial-pf-resolver-stale-override` (base `upstream/version-16` = v0.25.0; objetivo **0.25.1**)
**Tarea actual:** Fix del resolver de Print Format comercial ante `proposal_print_format` stale/inelegible en Borrador.

---

## Recuperación rápida

Estoy trabajando en:
Corregir de forma genérica el manejo de `Quotation.proposal_print_format` cuando quedó apuntando a un
Print Format inelegible (inexistente / `doc_type != Quotation` / `disabled=1`) — p. ej. tras versionar
un PF (base → V1). Antes: `dynamic_commercial_print_format` devolvía el override sin validar → `get_print`
lanzaba `DoesNotExistError` al usar "Descargar PDF Borrador".

Plan que estoy siguiendo:
Opción C aprobada = resolver tolerante en Draft + sync que repuebla el override inelegible, con un helper
único de elegibilidad. Sin tocar documentos congelados (ADR-0011).

Objetivo inmediato:
`/ship` completo hasta release v0.25.1 contra `version-16`.

Criterio de avance:
Suite verde (salvo #60 ambiental), CI verde, auditoría de aditividad aprobada (ADITIVO/SEGURO).

---

## Estado actual

### Ya cerrado
- `is_eligible_print_format(pf_name)`: fuente única de elegibilidad (delega en `get_print_format_status`).
- `dynamic_commercial_print_format`: primer candidato ELEGIBLE entre override → Template → DEFAULT; si
  ninguno elegible, `frappe.throw` claro. Path congelado (`resolve_commercial_print_format` con
  `proposal_effective_print_format`) sin cambios.
- `sync_proposal_print_format_from_template`: repuebla el override también cuando quedó inelegible; nunca
  pisa una selección manual válida; solo si el PF de la plantilla es elegible.
- Tests: 11 casos nuevos en `test_print_format_resolution.py` (20/20 en el módulo; suite 762/763, única
  falla ambiental #60 `test_09b`).
- Bump `__version__` 0.25.1 + CHANGELOG.

### Pendiente inmediato
1. `/ship` completo (commit → push → pr → merge --release) → tag/Release v0.25.1.
2. Aparte (pack privado, otro repo): corte 1.27.0 con el delta LOAS/PF/Section/Payment Term.

### No repetir
- El fix es de la APP; los cambios de contenido (Item LOAS, Sections, PF html, Payment Term) viven en el
  PACK privado, no en este repo.
- `test_09b` (#60) falla solo local (`allow_multiple_items=1`); pasa en CI.

---

## Decisiones vigentes
- Elegibilidad de PF centralizada en un único helper; no duplicar el criterio (query Link / validación /
  status / resolver / sync lo comparten).
- Congelados intactos: `proposal_effective_print_format` conserva prioridad absoluta (ADR-0011).

---

## Archivos relevantes ahora
### Leer primero
- `erpnext_proposals/erpnext_proposals/utils/print_format.py` (resolver + sync + `is_eligible_print_format`).
- `erpnext_proposals/erpnext_proposals/tests/test_print_format_resolution.py`.

### No tocar
- PF html / Sections / Template / pack (viven en el pack privado), producción, `facturacion_mexico`.

---

## Riesgos / cuidados
- Auditoría de retroactividad aprobada: no-recurrentes byte-equivalentes a 1.26.0; 0 submitted con V1 en
  producción; PF base e Implementación intactos. Veredicto ADITIVO/SEGURO.

## Información faltante
- Ninguna para cerrar el PR.
