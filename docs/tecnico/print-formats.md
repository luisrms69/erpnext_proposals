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
