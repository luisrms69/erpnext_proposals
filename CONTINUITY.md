# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-08-31
**Rama activa:** `fix/restore-commercial-preview-printview` (base `upstream/version-16` = **v0.11.3**)
**Tarea actual:** Preparar **v0.11.4** = **v0.11.2 + un botón nuevo de PDF Borrador**. Corrige la regresión
que introdujo v0.11.3 en el botón *Imprimir Propuesta Comercial*. Sin commit/push/PR aún.

---

## Recuperación rápida

Estoy trabajando en:
v0.11.3 (PR #51) cambió **incorrectamente** el botón *Imprimir Propuesta Comercial*: pasó de abrir el
preview HTML (`/printview`) a descargar un PDF directo, eliminando la revisión preliminar en HTML que el
cliente necesita en Borrador. v0.11.4 restaura ese preview **y** añade, por separado, un botón para
descargar un PDF claramente marcado como **BORRADOR** mientras la propuesta sigue editable.

Plan que estoy siguiendo:
Corrección **manual** archivo por archivo (sin `git revert/reset/restore/checkout`). Referencia funcional
= **v0.11.2** (commit `732fa9d`). Entregar auditoría v0.11.2 vs v0.11.4 (categoría D = 0) → autorización
→ `/ship commit` → push → PR → release.

Objetivo inmediato:
Entregar el paquete de auditoría y esperar autorización. NO commit/push/PR/deploy.

Criterio de avance:
Tests nuevos verdes + suites relacionadas; `mkdocs --strict` limpio; linters OK; y la auditoría demuestra
que **lo único nuevo** frente a v0.11.2 es el PDF Borrador.

---

## Los tres flujos (deben quedar separados)

1. **Preview HTML (Borrador)** — botón *Imprimir Propuesta Comercial*:
   `generate_pdf_with_resync` → `get_effective_commercial_print_format` → `/printview` → `window.open`.
   **Recupera el comportamiento de v0.11.2.** No descarga PDF.
2. **PDF Borrador (Borrador)** — botón NUEVO *Descargar PDF Borrador* (solo `workflow_state === "Borrador"`,
   `docstatus === 0`): `generate_pdf_with_resync` → endpoint `download_commercial_draft_pdf` →
   `resolve_commercial_print_format` → `render_proposal_pdf` (respeta gotenberg-v1/legacy). Descarga
   `BORRADOR - Propuesta Comercial - <Quotation>.pdf`. **No** adjunta, **no** congela, **no** cambia estado,
   **no** invoca `attach_proposal_pdfs`.
3. **Documento formal (Borrador → En Revisión)** — flujo AUTOMÁTICO **intacto** (v0.11.2):
   `attach_proposal_pdfs(doc)` → `_attach_pdf(...)` → `render_proposal_pdf(doc, print_format)` → renderer
   profile → PDF privado adjunto. **NO se toca** `workflow_validations.py`, `quotation.py`, `renderer.py`,
   `gotenberg.py`, `official_document_protection.py`, `hooks.py`, Print Formats ni pack privado.

---

## Cambios de v0.11.4 (respecto a v0.11.2)

- `public/js/quotation.js` — botón comercial = v0.11.2; **+ botón nuevo** *Descargar PDF Borrador* (Borrador).
- `utils/print_format.py` — **+ endpoint** `download_commercial_draft_pdf` (renombrado desde el
  `download_commercial_pdf` de v0.11.3, ahora con semántica y filename de BORRADOR).
- `tests/test_commercial_draft_pdf.py` — cobertura del endpoint borrador + verificación por fuente del JS
  (preview HTML preservado, botón borrador solo en Borrador, sin nombre viejo `download_commercial_pdf`).
- `docs/referencia/api.md`, `docs/tecnico/print-formats.md`, `docs/usuario/generar-enviar-propuesta.md` —
  documentan los tres flujos; se elimina toda afirmación de v0.11.3 de que el botón comercial descarga PDF.
- `erpnext_proposals/__init__.py` — `0.11.3 → 0.11.4`.

> El nombre `download_commercial_pdf` de v0.11.3 **desaparece por completo** (código, JS, tests, docs).
> La afirmación de v0.11.3 *"el botón comercial nunca debe abrir /printview"* era **incorrecta** y se retira.

---

## Estado / pendientes

- **Staging** sigue en **v0.11.2**; el usuario ya verificó que el **PDF formal** de v0.11.2 funciona.
- Pendiente tras liberar v0.11.4: actualizar staging **una sola vez** y validar los tres flujos
  (preview HTML, PDF Borrador, documento formal) end-to-end con Gotenberg real.
- Claude **no** ejecuta en staging: el usuario corre y pega salida.

---

## No repetir
- El botón *Imprimir Propuesta Comercial* **debe** abrir `/printview` (preview HTML) — no descargar PDF.
- El PDF Borrador **nunca** debe confundirse con el oficial (prefijo `BORRADOR`, sin adjuntar).
- No tocar el flujo formal de *En Revisión*, ni Frappe/ERPNext core, ni interceptar `download_pdf` nativo.
