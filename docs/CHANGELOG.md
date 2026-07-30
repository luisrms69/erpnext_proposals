# Changelog — erpnext_proposals

## [No liberado]

### Added
- Impuesto automático en Quotation reutilizando **por import** (read-only) la resolución fiscal de
  `facturacion_mexico` (Centro de Costos → Branch → zona → STCT). Adapter exclusivo en
  `erpnext_proposals` (`utils/quotation_tax.py`, hook `Quotation.before_validate`); `facturacion_mexico`
  **no se modifica**. Solo aplica con `quotation_to == "Customer"`; no-op suave si falta configuración;
  respeta selección manual de `taxes_and_charges`; sin la validación SAT estricta de Sales Invoice —
  ver ADR-0008.
- Resolución del Print Format comercial (override → Proposal Template → default) con congelamiento
  del formato efectivo — ver ADR-0005.
- Loader genérico de catálogos por ruta externa y separación app-genérica vs personalización privada
  por cliente — ver ADR-0006.

### Docs
- `tecnico/print-formats.md`: sección de resolución y congelamiento del formato comercial; `hide_title`
  y estructura del snapshot de secciones; convención del umbral `sequence >= 500` sin referirse a
  templates "instalados".
- `tecnico/arquitectura.md`: loader de catálogos (incluye Items, Print Formats y Payment Terms /
  Payment Terms Templates); modelo de contenido editorial en `Item` y su copia congelada en
  `Quotation Item`; `hide_title` en `Proposal Template Section`; los Templates/Sections se cargan por
  catálogo, **no** por `install.py`.
- `tecnico/setup.md`, `tecnico/despliegue-produccion.md`, `usuario/flujo-operativo.md`: corregido que
  `after_install` **no** siembra contenido comercial (solo Desktop Icon); el contenido se carga con el
  loader del catálogo. `facturacion_mexico` agregado como `required_app`.
- ADR-0005 y ADR-0006.

## [0.0.1] — 2026-05-18

### Added
- Scaffold inicial del app
- Estructura de documentación (docs/adr/)
- Configuración Claude Code (.claude/)
- Site de desarrollo: proposals.dev
- Site de tests: test-erpnext_proposals.localhost
