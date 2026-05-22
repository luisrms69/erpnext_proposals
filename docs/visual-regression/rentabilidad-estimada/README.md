# Visual Regression — Rentabilidad Estimada

PDFs de referencia para el Print Format `Rentabilidad Estimada`.

## Propósito

Estos archivos son evidencia visual de cada iteración del Print Format.
Permiten comparar visualmente cambios antes de mergear y detectar regresiones.

> **El PDF baseline es evidencia visual de referencia, no fuente de verdad.**
> La fuente de verdad del Print Format sigue siendo `rentabilidad_estimada.json` versionado en Git.

## Convención de nombres

```
rentabilidad-estimada-<componente>-v<version>.pdf
rentabilidad-estimada-baseline-<YYYY-MM-DD>.pdf
```

## Flujo obligatorio para cambios al Print Format

Igual que para Propuesta Comercial — ver `docs/visual-regression/propuesta-comercial/README.md`.

```
1. Crear rama feature/print-*
2. Editar solo rentabilidad_estimada.json (CSS/HTML/Jinja)
3. bench --site proposals.dev execute "frappe.reload_doc('ERPNext Proposals', 'Print Format', 'Rentabilidad Estimada', force=True)"
4. Generar PDF y revisar visualmente
5. Commit con prefijo style(print): o feat(print):
6. Agregar PDF de evidencia a esta carpeta
7. PR con PDF adjunto en la descripción
8. Merge
9. En producción: bench --site <site> execute "frappe.reload_doc(..., force=True)"
```

## Regla de producción

**Nunca editar el Print Format directamente en ERPNext UI como cambio permanente.**

El JSON en Git es siempre la fuente de verdad.

## PDFs en esta carpeta

| Archivo | Rama | PR | Descripción |
|---|---|---|---|
| `rentabilidad-estimada-baseline-2026-05-21.pdf` | `feature/pdf-polish` | #15 | Baseline: CSS variables, sección Alcance Cotizado, tabla de headers corregida |
