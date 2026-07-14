# Print Formats — Desarrollo y mantenimiento

Guía técnica para modificar los dos Print Formats del app:
- **Propuesta Comercial** — PDF de propuesta para el cliente
- **Rentabilidad Estimada** — PDF interno de análisis de costos

---

## Regla de producción

**Nunca editar un Print Format directamente en ERPNext UI como cambio permanente.**

Si se prueba algo en UI → replicar en el JSON → commit → PR.

Los JSONs en Git son siempre la fuente de verdad:
- `erpnext_proposals/print_format/propuesta_comercial/propuesta_comercial.json`
- `erpnext_proposals/print_format/rentabilidad_estimada/rentabilidad_estimada.json`

---

## Flujo obligatorio para cambios

```
1. Crear rama feature/print-*
2. Editar solo el JSON del Print Format (CSS/HTML/Jinja)
3. Recargar el formato en el site:
   bench --site proposals.dev execute "frappe.reload_doc('ERPNext Proposals', 'Print Format', '<Nombre>', force=True)"
4. Generar PDF de prueba y revisar visualmente
5. Commit con prefijo style(print): o feat(print):
6. Guardar PDF de evidencia en working_docs/archive/visual-regression/<formato>/
7. PR con PDF adjunto en la descripción
8. Merge
9. En producción:
   bench --site <site> execute "frappe.reload_doc('ERPNext Proposals', 'Print Format', '<Nombre>', force=True)"
```

---

## Comandos de recarga por formato

```bash
# Propuesta Comercial
bench --site proposals.dev execute \
  "frappe.reload_doc('ERPNext Proposals', 'Print Format', 'Propuesta Comercial', force=True)"

# Rentabilidad Estimada
bench --site proposals.dev execute \
  "frappe.reload_doc('ERPNext Proposals', 'Print Format', 'Rentabilidad Estimada', force=True)"
```

---

## Anatomía del PDF — Propuesta Comercial

El Print Format `Propuesta Comercial` renderiza en un **orden fijo de bloques**. El contenido
narrativo proviene de las secciones del template (`Proposal Template Section`), pero el
**alcance** (Scope Items) y la **inversión** (líneas de la cotización) se insertan en
posiciones fijas del Jinja, **no** como secciones del template.

Orden de render:

| # | Bloque | Origen del contenido |
|---|---|---|
| 1 | Portada | Datos de la cotización + logo |
| 2 | Resumen Ejecutivo | Sección con `is_executive_summary = 1` |
| 3 | Índice | Generado automáticamente |
| 4 | Secciones narrativas | Secciones del template con **`sequence < 500`** |
| 5 | **Plan de Trabajo** | **Scope Items** (`quotation_scope_items`), agrupados por fase |
| 6 | **Entregables** | Scope Items que tienen `deliverable` |
| 7 | **Inversión** | Líneas de la cotización (`doc.items`) |
| 8 | Secciones legales / comerciales | Secciones del template con **`sequence >= 500`** |
| 9 | Bloque de aceptación | Espacio de firma |

### Regla del umbral `sequence >= 500`

El número **500** es el umbral que decide **dónde** aparece una sección del template respecto
al alcance y la inversión:

- Sección con `sequence < 500` → se renderiza **antes** del Plan de Trabajo (bloque 4).
- Sección con `sequence >= 500` → se renderiza **después** de la Inversión (bloque 8).

Es una convención definida en el Jinja de `propuesta_comercial.json` (buckets
`body_sections` / `late_sections`). Hoy los 3 templates instalados usan sequences 10–100,
por lo que **todas** sus secciones caen antes del alcance; nada queda después salvo Inversión
y Aceptación.

**Para colocar una sección después del alcance** (ej. términos legales, garantías,
condiciones comerciales), asignarle `sequence >= 500` en el `Proposal Template Section`.

> El umbral 500 vive únicamente en el Jinja del Print Format. Al editar templates, respetar
> esta convención — de lo contrario una sección "legal" aparecerá en medio del cuerpo.

---

## Convención de nombres para evidencia visual

Los PDFs de evidencia se guardan en `working_docs/archive/visual-regression/<formato>/`:

```
propuesta-comercial-<componente>-v<version>.pdf
propuesta-comercial-baseline-<YYYY-MM-DD>.pdf

rentabilidad-estimada-<componente>-v<version>.pdf
rentabilidad-estimada-baseline-<YYYY-MM-DD>.pdf
```

Ejemplos:
```
propuesta-comercial-baseline-2026-05-21.pdf    ← estado completo al cerrar la rama
propuesta-comercial-investment-v1.pdf          ← sección Inversión, primera versión
rentabilidad-estimada-baseline-2026-05-21.pdf  ← baseline con tabla Alcance Cotizado
```

---

## Archivos relevantes

| Archivo | Propósito |
|---|---|
| `propuesta_comercial.json` | Fuente de verdad del Print Format de propuesta |
| `rentabilidad_estimada.json` | Fuente de verdad del Print Format de rentabilidad |
| `utils/printing.py` | Helpers Jinja: `render_section_content`, `parse_json`, `get_logo_url` |
| `report/profitability_estimate/` | Fuente de datos para Rentabilidad Estimada |
| `working_docs/archive/visual-regression/` | PDFs de evidencia histórica por formato |
