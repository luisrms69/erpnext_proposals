# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-22
**Rama activa:** `feat/quotation-proposal-content-ux` (base `upstream/version-16` = v0.28.0)
**Tarea actual:** UX "Contenido de propuesta" + 2 fixes de QA (orden semántico de `proposal_sections`; preview/PDF de solo lectura).

---

## Recuperación rápida

Estoy trabajando en:
Mejora de UX para editar/revisar el contenido narrativo de una propuesta dentro de la Quotation. Fuente
única = `Quotation.proposal_sections` (child `Proposal Quotation Section`). Más dos correcciones de QA
sobre esa misma rama, con tests independientes.

Plan que estoy siguiendo:
Pestaña **Contenido de propuesta** (grid simple + form hijo nativo; `sequence`/`proposal_section`/
`is_executive_summary` ocultos) + pestaña **Vista previa** (renderer de cliente que lee
`frm.doc.proposal_sections` en orden `idx`, sanitiza con `frappe.dom.remove_script_and_style`, re-render
al activar la pestaña).

Objetivo inmediato:
Commit local de los 2 fixes (hecho, sin push). Prueba manual del usuario en http://localhost:8405.

Criterio de avance:
Suite completa 798 OK / 1 skip; ruff+prettier OK; mkdocs strict OK. Los dos fixes con tests dedicados en
verde (8 + 3).

---

## Estado actual

### Ya cerrado (esta rama)
- **UX (commit f4dc9bc):** DocType `proposal_quotation_section.json` (grid simple), custom fields
  (`proposal_content_tab`/`proposal_preview_tab`/`proposal_preview_html`), renderer de Vista previa.
- **Fix 1 — orden SEMÁNTICO por `sequence` (no espejo de `idx`):** el PF ancla el bloque de
  Items/Inversión en `sequence == 500` (`<500` antes, `>=500` después). `_sync_proposal_section_sequence`
  reasigna `sequence` por **PUNTO MEDIO entre vecinos** desde el orden visual; el drag puede cruzar la
  frontera 500; renumera preservando orden y lado de 500 si no hay hueco entero. Nunca `sequence=idx`,
  nunca 0/vacío. Corre en TODO guardado en Borrador (antes de los early-return de `validate`).
- **Fix 2 — preview/PDF de solo lectura:** `generate_pdf` (quotation.js) ya no dispara resync; los
  botones de Vista previa/Descargar solo persisten ediciones y renderizan.
  `resync_scope_from_catalog` deja de re-materializar `proposal_sections` (narrativa = fuente única,
  ADR-0022). El resync explícito sigue sincronizando scope/costos/economía.
- **Tests:** `TestProposalSectionOrder` (8: reorden <500 y >=500, cruce arriba/abajo, ad-hoc en rango,
  borrado) + `TestPreviewPdfReadOnly` (3: resync y lector no mutan la narrativa).
  `test_proposal_sections_materialize.test_05` actualizado al nuevo contrato (resync NO re-pulla).

### Pendiente inmediato
1. Prueba manual (usuario): aplicar template → editar/arrastrar (incluido cruce de la frontera de
   Inversión) → Vista previa refleja el orden → guardar → PDF conserva orden → botón de resync no altera
   la narrativa.
2. Bump de versión al preparar el PR (feature → MINOR, objetivo 0.29.0 desde 0.28.0). No bump en WIP.

### No repetir / atención
- El render del preview ordena por `idx` (estado del form); `sequence` es el orden persistido para
  PF/`get_sections_snapshot`. El sync corre en `validate` (Borrador).
- Para que el sync (Python) tome efecto en el server dev puede requerir `/server-restart`.
- Los fixtures de test usan nombres `_Test UXB …` (los `_Test UX …` previos quedaron persistidos con
  otra definición en el site de tests).

---

## Decisiones vigentes
- Fuente única del contenido efectivo = `Quotation.proposal_sections`; sin segunda copia para el preview.
- `sequence` es dato SEMÁNTICO (posición real en el documento; frontera 500 del bloque de Items), no
  espejo de `idx`; se reasigna por punto medio en Borrador; oculto al usuario.
- Preview/PDF y `resync_scope_from_catalog` NUNCA reconstruyen la narrativa (ADR-0022).

## Información faltante
- Ninguna para el commit. Prueba manual y bump-para-PR pendientes.
