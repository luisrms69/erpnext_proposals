# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-22
**Rama activa:** `feat/quotation-proposal-content-ux` (base `upstream/version-16` = v0.28.0)
**Tarea actual:** UX "Contenido de propuesta" — edición y revisión de `Quotation.proposal_sections` con Frappe nativo.

---

## Recuperación rápida

Estoy trabajando en:
Mejora de UX acotada a cómo el usuario edita/revisa el contenido narrativo de una propuesta dentro de la
Quotation. Fuente única = `Quotation.proposal_sections` (child `Proposal Quotation Section`). Sin tocar
freeze/costos/economía/pack/migraciones ajenas.

Plan que estoy siguiendo:
Pestaña dedicada **Contenido de propuesta** (grid simple: Título · Ocultar título; edición en form hijo
nativo; `sequence`/`proposal_section`/`is_executive_summary` ocultos) + pestaña **Vista previa** (HTML
field + renderer de cliente que lee `frm.doc.proposal_sections` en orden `idx`, sanitiza con
`frappe.dom.remove_script_and_style`, re-render al activar la pestaña → refleja arrastres sin guardar).
Orden por arrastre (idx); en Borrador `validate` sincroniza `sequence` **solo cuando difiere** (preserva
valores del Template, no expone `sequence`). `custom_content`/`use_custom_content` conservados (contenido
inicial específico por Template). Secciones ad-hoc con `proposal_section` vacío permitidas.

Objetivo inmediato:
Commit local de este bloque (hecho, sin push). Prueba manual del usuario en http://localhost:8405.

Criterio de avance:
Suite completa 793 OK / 1 skip; ruff+prettier; mkdocs strict OK; migrate limpio (dev+test); tab membership
verificada (Contenido de propuesta = solo proposal_sections; Vista previa = solo el HTML field).

---

## Estado actual

### Ya cerrado (esta rama)
- DocType `proposal_quotation_section.json`: in_list_view=title+hide_title; sequence/proposal_section/
  is_executive_summary `hidden`; labels ES.
- `fixtures/custom_field.json`: +Tab Break `proposal_content_tab` (aloja `proposal_sections`) +Tab Break
  `proposal_preview_tab` +HTML `proposal_preview_html`; `hooks.py` allowlist +3 fieldnames.
- `utils/quotation.py`: `_sync_proposal_section_sequence()` (Borrador; renumera solo si idx≠sequence) +
  llamada en `on_quotation_validate`.
- `public/js/quotation.js`: `render_proposal_preview()` + handlers (refresh, content/title/hide_title,
  add/remove) + re-render al activar la pestaña Vista previa (delegado por `data-fieldname`).
- Tests: `test_proposal_content_ux.py` (6). Docs: crear-propuesta.md (Paso 5), doctypes.md, arquitectura.md.

### Pendiente inmediato
1. Prueba manual (usuario): aplicar template → editar en Contenido de propuesta → arrastrar/reordenar → NO
   guardar → Vista previa refleja el nuevo orden → guardar → sequence sincronizado → Print/PDF conserva orden.
2. Bump de versión al preparar el PR (feature → MINOR, objetivo 0.29.0 desde 0.28.0). No bump en WIP.
3. Docs ADR: evaluar si esta UX amerita ADR propio (por ahora cubierto en arquitectura.md).

### No repetir / atención
- El render del preview ordena por `idx` (estado actual del form), NO por `sequence` (que es el orden
  persistido para PF/readers). El sync `sequence=idx` corre en `validate` (Borrador).
- Para que el sync (Python) tome efecto en el server dev puede requerir `/server-restart`; el meta ya está
  migrado y el JS ya está built.

---

## Decisiones vigentes
- Fuente única del contenido efectivo = `Quotation.proposal_sections`; sin segunda copia para el preview.
- `sequence` es el orden canónico persistido (PF/`get_sections_snapshot`); se sincroniza desde `idx` en
  Borrador solo cuando difiere; oculto al usuario.
- `custom_content`/`use_custom_content` (en Proposal Template Section) se conservan: contenido inicial
  específico por Template.

## Información faltante
- Ninguna para el commit. Prueba manual y bump-para-PR pendientes.
