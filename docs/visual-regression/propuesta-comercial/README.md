# Visual Regression — Propuesta Comercial

PDFs de referencia para el Print Format `Propuesta Comercial`.

## Propósito

Estos archivos son evidencia visual de cada iteración del Print Format.
Permiten comparar visualmente cambios antes de mergear y detectar regresiones.

> **El PDF baseline es evidencia visual de referencia, no fuente de verdad.**
> La fuente de verdad del Print Format sigue siendo `propuesta_comercial.json` versionado en Git.

## Convención de nombres

```
propuesta-comercial-<componente>-v<version>.pdf
propuesta-comercial-baseline-<YYYY-MM-DD>.pdf
```

Ejemplos:
```
propuesta-comercial-baseline-2026-05-21.pdf   ← estado completo al cerrar la rama
propuesta-comercial-cover-v1.pdf              ← portada, primera versión
propuesta-comercial-exec-summary-v1.pdf       ← resumen ejecutivo como página propia
propuesta-comercial-sections-v1.pdf           ← tipografía de secciones
```

## Flujo obligatorio para cambios al Print Format

```
1. Crear rama feature/print-*
2. Editar propuesta_comercial.json (solo CSS/HTML/Jinja)
3. bench --site proposals.dev execute "frappe.reload_doc(..., force=True)"
4. Generar PDF de prueba y revisar visualmente
5. Commit pequeño con prefijo style(print):
6. Agregar PDF de evidencia a esta carpeta
7. PR con PDF adjunto en la descripción
8. Merge
9. En producción: bench --site <site> execute "frappe.reload_doc(..., force=True)"
```

## Regla de producción

**Nunca editar el Print Format directamente en ERPNext UI como cambio permanente.**

Si se prueba algo en UI → replicar en `propuesta_comercial.json` → commit → PR.

El JSON en Git es siempre la fuente de verdad.

## PDFs en esta carpeta

| Archivo | Rama | PR | Descripción |
|---|---|---|---|
| `propuesta-comercial-baseline-2026-05-21.pdf` | `feature/pdf-polish` | #15 | Baseline antes de sección Inversión: portada, resumen ejecutivo, tipografía, tablas |
| `propuesta-comercial-investment-v1.pdf` | `feature/pdf-polish` | #15 | Inversión rediseñada: tabla comercial, total full-width, condiciones de pago como tabla |
