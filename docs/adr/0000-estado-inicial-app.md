# ADR-0000: Estado inicial — erpnext_proposals

**Fecha:** 2026-05-18
**Status:** Activo

## Contexto

App nueva creada como parte del ecosistema Buzola sobre frappe-bench-v16.

Propuestas comerciales profesionales sobre ERPNext Quotation. Agrega una capa
de estructura narrativa (Proposal Templates, Proposal Sections, Scope Items) encima
del flujo nativo de cotización, permitiendo generar PDFs de propuesta profesionales
sin reemplazar Quotation Items ni crear sistemas paralelos de precios.

## Decisiones iniciales

- Bench: frappe-bench-v16 (Frappe 16.18.2, ERPNext 16.18.3)
- Branch protegida: version-16 (estándar Frappe upstream)
- Site de desarrollo: proposals.dev → localhost:8405
- Site de tests: test-erpnext_proposals.localhost
- Apps requeridas: erpnext
- GitHub: https://github.com/luisrms69/erpnext_proposals

## Arquitectura aprobada (v2.0)

- Extender ERPNext Quotation con Custom Fields (no reemplazar)
- DocTypes propios: Proposal Section, Proposal Template, Scope Item, Quotation Scope Item (child)
- Quotation Items sigue siendo la única tabla comercial
- Scope Items = alcance narrativo/técnico congelado (sin precios ni costos propios)
- Print Format Jinja para PDF profesional (8 secciones ordenadas por SOW)
- ERPNext maneja: precios, costos, impuestos, Designation, Activity Type

## Notas

Documentar decisiones arquitectónicas relevantes en ADRs subsiguientes.
Ver conversación de diseño en ChatGPT proyecto erpnext_proposals.
