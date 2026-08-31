# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-08-30
**Rama activa:** `fix/commercial-pdf-uses-renderer` (base `upstream/version-16` = **v0.11.2**)
**Tarea actual:** Cerrar el fix público **v0.11.3** — el botón *Imprimir Propuesta Comercial* deja de abrir `/printview` y descarga el PDF por el flujo oficial del renderer. Commit ✓ + push ✓; PR en creación.

---

## Recuperación rápida

Estoy trabajando en:
El defecto por el que el botón *Imprimir Propuesta Comercial* abría `/printview` (`window.open`) y
**saltaba** `render_proposal_pdf()` — y por tanto el renderer profile (`gotenberg-v1`/`legacy`,
ADR-0015). En `SAL-QTN-2026-00013` el PF efectivo resolvía `gotenberg-v1`, pero el botón nunca lo usaba.

Plan que estoy siguiendo:
Flujo `/ship` de v0.11.3: commit ✓ → push ✓ → **pr** (base `version-16`). Tras merge (lo hace el
usuario): `/sync-check` → `/ship release`. Después: **actualizar staging** para la prueba **E2E real
desde el botón**.

Objetivo inmediato:
Crear el PR hacia `version-16`. No abrir otros frentes hasta el merge.

Criterio de avance:
Tests A–H verdes (8/8) + suites relacionadas (renderer 35, resolution 11, selector 10, protection 10);
`mkdocs build --strict` limpio; linters OK.

---

## Estado actual

### Ya cerrado
- **v0.11.0** (ADR-0015): renderer PDF desacoplado. **v0.11.1**: loader siembra `proposal_renderer_profile`.
  **v0.11.2**: renderer Gotenberg respeta print-media y márgenes del Print Format. Todos released.

### En progreso (este PR — v0.11.3)
- **Endpoint whitelisted** `download_commercial_pdf(quotation)` en `utils/print_format.py`: valida
  permiso de lectura → `resolve_commercial_print_format(doc)` → `render_proposal_pdf(doc, pf)` → devuelve
  descarga (`type="download"`, `application/pdf`). No adjunta como documento oficial.
- **`quotation.js`**: el botón comercial usa `open_url_post` al endpoint (POST + CSRF); ya **no** arma
  `/printview` ni `window.open`. Se conserva `generate_pdf_with_resync` (resync en Borrador).
  **Rentabilidad Estimada sin cambios.**
- **Docs**: `tecnico/print-formats.md`, `referencia/api.md`, `usuario/generar-enviar-propuesta.md`.
- **Bump** `0.11.2 → 0.11.3` (PATCH).

### Pendiente inmediato
1. `/ship pr` (base `version-16`) → merge por el usuario → `/sync-check` → `/ship release` (tag +
   GitHub Release `v0.11.3`).
2. **Actualizar staging** (`erpstagingacti.buzola.mx`, bench `/home/erpnext/frappe-bench`) y correr la
   **prueba E2E real desde el botón** (Gotenberg ya desplegado en el host).

### No repetir
- El botón comercial **debe** pasar siempre por `render_proposal_pdf()`; nunca `/printview` para el PDF comercial.
- No cambiar `renderer.py`, `gotenberg.py`, el Print Format ni el pack privado en este frente.
- El pack Actiglobal es **file-based** (NO Git / NO `/ship`).
- Claude **no** corre en staging: el usuario ejecuta y pega salida.

---

## Decisiones vigentes (v0.11.3)
- **Resolución del PF en servidor**, dentro del endpoint: congelada → `proposal_effective_print_format`;
  Borrador → override → Template → default. Evita divergencia cliente/servidor.
- **`render_proposal_pdf()` es la única puerta** al motor: el endpoint no llama a `GotenbergClient` ni
  duplica lógica; el dispatch `gotenberg-v1`/`legacy` (ADR-0015) se aplica solo.
- **Preview/descarga, no oficial**: este botón no adjunta el PDF; el flujo de congelado/adjunto
  (`quotation.py::_attach_pdf`) ya usaba `render_proposal_pdf()` y no se tocó.
- **Entrega por descarga** (`open_url_post` + `type="download"`): reemplaza la apertura de pestaña printview.

---

## Archivos relevantes ahora

### Leer primero
- `erpnext_proposals/erpnext_proposals/utils/print_format.py` — `download_commercial_pdf`,
  `resolve_commercial_print_format`, `render_proposal_pdf`.
- `erpnext_proposals/public/js/quotation.js` — botón *Imprimir Propuesta Comercial* (bloque `st.commercial`).
- `erpnext_proposals/erpnext_proposals/tests/test_commercial_pdf_download.py` — tests A–H.

### No tocar
- `renderer.py`, `gotenberg.py`, Print Format, pack privado, infra/site config. `one_offs/` (ignorado).

---

## Riesgos / cuidados
- La prueba E2E definitiva es en **staging** con Gotenberg real; localmente se validó por unit tests
  con HTTP mockeado (no se ejercitó Gotenberg real desde el botón).
- Tras el merge, el release **no** está cerrado hasta tag + GitHub Release `v0.11.3` alineados.

---

## Información faltante
- Ninguna para crear el PR de v0.11.3.
