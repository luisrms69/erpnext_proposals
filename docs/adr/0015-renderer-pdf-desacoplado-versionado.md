# ADR-0015: Renderer PDF desacoplado y versionado para Print Formats operativos

**Fecha:** 2026-08-28
**Status:** Aceptado — base implementada; sin formatos adoptándola aún
**Ámbito:** erpnext_proposals (capacidad genérica; nada específico de cliente)

---

## Contexto

Los Print Formats de propuesta se generan hoy con **wkhtmltopdf** a través de
`frappe.utils.pdf.get_pdf()`. Ese motor vive **dentro** del pipeline de Frappe, por lo que su
comportamiento puede cambiar con una actualización de Frappe/ERPNext, de wkhtmltopdf o de librerías
del entorno.

La necesidad de negocio es concreta: **un Print Format que hoy genera correctamente no debe cambiar su
resultado visual mañana porque se actualice Frappe/ERPNext o alguna librería** — ni para el histórico
ni para las **propuestas nuevas** que un cliente siga generando sobre un formato operativo (v1).

### Contexto técnico del incidente (no es premisa de este ADR)

- Un mismo formato produjo **distinto resultado PDF entre entornos** (local vs staging).
- En staging el defecto (pérdida del logo/header en varias páginas) **ya está presente en el PDF RAW**
  producido por wkhtmltopdf, antes de cualquier merge.
- Se **descartaron** como causa: `pypdf`, las rutas de los assets y la disponibilidad HTTP de los assets.
- La **causa raíz puntual** del incidente queda como **diagnóstico separado** y **no** es premisa de
  esta decisión: el problema arquitectónico (acoplamiento del motor HTML→PDF a versiones) existe con
  independencia de esa causa.

---

## Decisión

Se adopta un **renderer PDF desacoplado y versionado** como capacidad **genérica** de
`erpnext_proposals`, con el siguiente MVP:

1. **Gotenberg** como servicio de rendering, usado a través de una **abstracción de renderer** en
   `erpnext_proposals`.
2. La **imagen Docker de Gotenberg/Chromium se pinea por versión** (tag fijo, sin auto-update).
3. Cada Print Format liberado referencia un **`renderer_profile`** (p. ej. `gotenberg-v1`) que
   determina la imagen/motor y sus opciones de render.
4. El **`renderer_profile` de un Print Format operativo es inmutable**: es la misma regla que ya rige
   para un v1 ("un v1 nunca se altera"), aplicada también al motor de render.
5. Un **cambio de renderer o un cambio visual incompatible** implica un **nuevo Print Format/versión
   (v2)**; nunca se modifica silenciosamente un v1 operativo.
6. El **authoring del body** sigue siendo **HTML/CSS/Jinja + Proposal Sections/Templates**, igual que
   hoy. La elección del renderer es una costura interna, invisible para quien diseña el formato.
7. Los **assets y fuentes** necesarios para el render se **empaquetan/versionan** con el formato o el
   profile, para no depender de recursos mutables (`/files/...`) ni de fetch por red en tiempo de render.
8. **Header/footer usan recursos inline** — en particular el **logo como data-URI** y el CSS del header
   embebido —, por requerimiento del contexto Chromium de Gotenberg (que no carga recursos externos en
   header/footer).
9. Se **conserva la arquitectura de dos renders**:
   1. `cover.pdf` (portada full-bleed, sin header interior);
   2. `body.pdf` (cuerpo con header/footer repetidos);
   3. **merge final dentro de Gotenberg**, eliminando `pypdf` del **camino contractual** del PDF.
10. El **PDF final se archiva al freeze** de la propuesta como **artefacto histórico**.
11. La implementación es **general en `erpnext_proposals`**; el pack privado del cliente solo
    referencia un `renderer_profile`. Nada específico de cliente en el app público (ver ADR-0006).

---

## Frontera de la decisión (qué garantiza y qué no)

- **Garantiza:** la **estabilidad del paso HTML → PDF**, desacoplándolo de actualizaciones de
  Frappe/ERPNext y fijando el motor de render usado por cada versión de formato.
- **No pretende garantizar, en esta fase:** la reproducibilidad **absoluta** del paso **datos → HTML**
  frente a cualquier cambio futuro de Frappe/ERPNext (formato de fecha/moneda, helpers, etc.). Ese es
  un riesgo distinto y más raro, deliberadamente diferido.
- La inmutabilidad de **re-render** vive dentro de la ventana en que la imagen de Gotenberg pineada
  siga disponible; el **PDF archivado al freeze** es la garantía dura de "qué documento se emitió".

---

## Fuera de alcance (parqueado como hardening futuro, solo si aparece una necesidad real)

- Golden HTML.
- Comparación byte-a-byte del HTML.
- Freeze del HTML resuelto por cada propuesta.
- Matrices complejas de compatibilidad entre capas.
- Reproducción completa de versiones históricas de Frappe/ERPNext.
- Gobernanza avanzada de EOL de renderers.
- Cualquier sistema forense adicional.

Disparador para reconsiderar: si se **observa deriva real en la capa datos → HTML**, se atiende como
problema separado con su propio ADR; no es condición de esta implementación.

---

## Consecuencias

- Una actualización normal del ERP ya **no cambia el motor HTML→PDF** de un cliente operativo.
- Elimina la dependencia de `wkhtmltopdf` para los formatos que adopten este renderer y evita fetch
  HTTP de assets durante el render cuando estos se empaquetan/inlinean.
- **Costos:** un servicio adicional (Gotenberg en Docker) a operar/monitorear (endpoint interno, sin
  fetch externo); una **convención de header/footer** (data-URI + reglas Chromium) que el diseñador
  debe seguir en esa zona; y una **re-validación visual única** al portar un formato a Chromium — que,
  por ser cambio de motor, **es un v2**, nunca una auto-migración de un v1.
- Extiende de forma natural el versionado de Print Formats existente (ADR-0005/0011): además del
  formato efectivo congelado, un formato liberado fija su `renderer_profile`.

---

## Alternativas descartadas

- **Statu quo (wkhtmltopdf dentro de `get_pdf`):** el proceso HTML→PDF permanece acoplado al pipeline
  de Frappe y al entorno de ejecución, por lo que no ofrece el aislamiento requerido para formatos
  operativos.
- **Chrome nativo de Frappe (`pdf_generator = chrome`):** vive **dentro** de Frappe; un upgrade de
  Frappe puede alterar el pipeline y el Chromium manejado → **no aísla** del requisito crítico. Útil
  solo como arreglo interino del bug, no como garantía.
- **Reproducción forense completa** (golden-HTML + freeze de HTML por propuesta + reproducción del
  entorno histórico): excede la necesidad real actual; se parquea como hardening.

---

## Relación con otros ADR

- [ADR-0005](0005-resolucion-congelamiento-print-format.md) y
  [ADR-0011](0011-candado-print-formats-historicos.md) — versionado y congelamiento del Print Format;
  el `renderer_profile` inmutable es una extensión de esa misma regla.
- [ADR-0006](0006-separacion-app-generica-personalizacion-privada.md) — capacidad genérica en el app;
  branding/profiles concretos en el pack privado.
- [ADR-0012](0012-proteccion-eliminacion-pdfs-oficiales.md) — el PDF archivado al freeze como artefacto
  protegido.
- [ADR-0014](0014-render-portada-separada-merge.md) — la arquitectura de dos renders (portada + cuerpo)
  se conserva; el merge migra de pypdf al endpoint de Gotenberg.
