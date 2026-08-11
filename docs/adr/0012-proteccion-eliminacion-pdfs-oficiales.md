# ADR-0012: Protección contra eliminación accidental de los PDFs oficiales de la propuesta

**Fecha:** 2026-08-10
**Status:** Cerrado — vigente
**Rama:** feat/proposals-hardening → version-16

---

## Contexto

Al congelar una propuesta (Borrador → En Revisión), el flujo genera y adjunta a la Quotation dos PDFs
oficiales (`utils/quotation.py::attach_proposal_pdfs` / `_attach_pdf`): la **propuesta comercial**
(pública) y la **Rentabilidad Estimada** (privada). Son la evidencia formal de la propuesta emitida.

Hasta ahora nada impedía eliminarlos: el flag nativo de Frappe `protect_attached_files` no está activo
en Quotation, y cualquier usuario con acceso a la Quotation (Sales/Maintenance User o Manager, etc.)
podía borrar sus adjuntos. Además, esos borrados son irreversibles y alterarían el expediente de una
propuesta ya formalizada. El flag nativo, de activarse, bloquearía **todos** los adjuntos de la
Quotation, lo cual es demasiado amplio.

---

## Decisión

Protección **específica de los PDFs oficiales**, dentro de `erpnext_proposals` y sin tocar Frappe core:

1. **Marcador inequívoco (no por nombre):** Custom Field `File.is_proposal_official_document` (Check,
   read-only). Lo fija **exclusivamente** el flujo de generación (`_attach_pdf`) al adjuntar cada
   documento oficial. Extensible: cualquier File que el flujo marque queda protegido, sin hardcodear
   los dos PDFs actuales.
2. **Bloqueo de borrado:** hook `doc_events["File"]["on_trash"]`
   (`utils/official_document_protection.py::protect_official_document_on_trash`) que hace `frappe.throw`
   si el File está marcado. Es el punto de choke universal (cubre borrado desde UI `remove_attach`, API
   y bulk).
3. **Excepciones mínimas y explícitas:**
   - **`Administrator`** (usuario) puede eliminarlo deliberadamente. Ni System Manager ni usuarios
     ordinarios pueden.
   - El **flujo interno de regeneración** se exime mediante el flag `frappe.flags[INTERNAL_REPLACE_FLAG]`
     que `_attach_pdf` activa solo mientras reemplaza la versión previa. No es un mecanismo general para
     saltarse la protección.
4. **Independiente del `docstatus` de la Quotation:** la condición vive en el File. Tras **cancelar** la
   propuesta, el documento oficial sigue protegido.

Adicionalmente, se corrige `_attach_pdf` para localizar la versión previa por **prefijo de nombre**
(`{filename}%`) en vez de nombre exacto: `save_file` añade un hash al nombre, por lo que la búsqueda por
nombre exacto nunca casaba y se **duplicaban** los oficiales en cada regeneración.

---

## Consecuencias

- Los PDFs oficiales no pueden eliminarse por el flujo normal; solo `Administrator` o el propio flujo de
  regeneración.
- **No se tocan** los permisos generales de `File` ni otros adjuntos de la Quotation (los no marcados se
  borran normalmente). La **lectura/descarga** de los oficiales no se ve afectada (solo el borrado).
- La regeneración interna reemplaza correctamente sin autobloquearse ni duplicar.

---

## Alternativas descartadas

- **Flag nativo `protect_attached_files` en Quotation:** bloquea **todos** los adjuntos de toda
  Quotation submitted y requiere customizar el DocType globalmente. Demasiado amplio.
- **Identificación por nombre de archivo:** frágil (falsos positivos/negativos y el hash de `save_file`);
  se prefirió el marcador explícito.
- **Restricción por permisos/roles de `File`:** global y coarse; no distingue oficiales de otros
  adjuntos.

---

## Fuera de alcance

- Endurecimiento adicional de roles/permisos de `File` (se mantienen los permisos actuales de Frappe).
- La restricción de re-generación desde el botón `Propuesta` y el candado de Print Formats históricos son
  capacidades distintas (ver ADR-0011).
