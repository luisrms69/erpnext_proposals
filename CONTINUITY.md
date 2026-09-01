# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-01
**Rama activa:** `feat/sow-official-document` (base `upstream/version-16` = v0.15.0)
**Tarea actual:** SOW (Statement of Work) como **tercer documento oficial**, reutilizando exactamente el
mecanismo de la propuesta comercial (sin arquitectura paralela). Bump a **0.16.0**. Listo para `/ship`.

---

## Recuperación rápida

El SOW es **otra representación del mismo contenido congelado** de la Quotation: mismo `render_proposal_pdf`,
mismo snapshot/freeze, mismo `attach_proposal_pdfs`, misma protección histórica (ADR-0012), misma portada
separada (ADR-0014). Solo cambia el Print Format.

Capacidades **genéricas** añadidas (sin nombres hardcodeados):
- `Proposal Template.sow_print_format` (Link → Print Format, opcional). Vacío = no hay SOW.
- `resolve_sow_print_format` + `get_effective_sow_print_format` (whitelisted).
- SOW como 3er documento en `attach_proposal_pdfs` (Borrador → En Revisión adjunta comercial +
  rentabilidad + SOW, privados e inmutables).
- **Portada separada generalizada:** `_uses_separate_cover` aplica a cualquier documento oficial designado
  por la plantilla (comercial o SOW) cuando `separate_cover_page` está activo — sin ramas por tipo.
- Acciones de borrador: `download_sow_draft_pdf`, `download_rentabilidad_draft_pdf`.
- Loader carga `sow_print_format` en el Proposal Template.

## Botones (grupo Propuesta)
`Vista previa comercial` · `Descargar PDF comercial` · `Vista previa rentabilidad` ·
`Descargar PDF rentabilidad` · `Vista previa SOW` · `Descargar PDF SOW`.

## Estado
- Suite completa del app: **405 tests OK** (site de tests migrado). Ruff/prettier/`mkdocs --strict` verdes.
- El Print Format concreto del SOW y su cableado por plantilla viven en el **pack privado** (fuera de este
  repo), no en el app. El app solo aporta la capacidad genérica.
- Renderer real (Gotenberg) validado en el sitio de staging del cliente; 3 documentos oficiales coexisten.

## No repetir
- El SOW **no** es un mecanismo aparte: reutiliza el pipeline comercial. No crear renderer/flujo paralelo.
- La portada separada se decide por la configuración `separate_cover_page`, **no** por el nombre del PF.
- **Nunca** poner datos/identificadores de cliente en archivos trackeados del repo.
