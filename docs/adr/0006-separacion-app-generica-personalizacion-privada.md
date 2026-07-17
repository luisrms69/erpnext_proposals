# ADR-0006: Separación entre aplicación genérica y personalización privada por cliente

**Fecha:** 2026-07-17
**Status:** Cerrado — vigente
**Rama:** feat/proposal-project-task-integration → version-16

---

## Contexto

`erpnext_proposals` es un repo **público**. Las implementaciones reales incluyen contenido
identificable del cliente: catálogos editoriales, Print Formats branded (logos, imágenes, CSS,
composición extraída de sus Word), y ejemplos con nombres de cliente. Ese material **no puede**
entrar al repo público, pero el app sí debe poder cargarlo/aplicarlo por sitio.

---

## Decisión

**En el repo (genérico, versionable):**

- Loader de catálogos **genérico** `catalog_data/catalog_loader.py` — recibe `catalog_path`, es
  idempotente, `dry_run` por defecto, transaccional, versiona conflictos y reporta
  (creados/actualizados/reutilizados/sin cambios). Sin nombres ni rutas de cliente.
- `catalog_data/sample_catalog.json` — catálogo ficticio para demo/tests.
- Print Format comercial **genérico** (`Propuesta Comercial`, sin branding; logo heredado de
  `Company.company_logo`) como default del sistema — ver [ADR-0005](0005-resolucion-congelamiento-print-format.md).
- Tests y documentación genéricos.

**Fuera del repo (privado del cliente):**

- Catálogo real (contenido editorial), assets (logos/imágenes/marcas), Print Formats branded
  (HTML/Jinja/CSS/JSON), instaladores `one_offs/` específicos, PDFs de referencia/render, y
  evidencias/comparativas. Viven en el espacio privado del cliente y se aplican por sitio.

**Gates de protección:**

- `.gitignore` excluye `catalog_data/*_catalog.json` (salvo `sample_catalog.json`) y `.client-blocklist`.
- `one_offs/` nunca se commitea (lo excluye el flujo `/ship`).
- El flujo `/ship` corre un gate de datos de cliente antes de publicar.

Uso del loader:

```
bench --site <site> execute erpnext_proposals.erpnext_proposals.catalog_data.catalog_loader.run \
  --kwargs "{'catalog_path': '<ruta externa>', 'dry_run': False}"
```

---

## Consecuencias

- El app se puede publicar sin filtrar información de cliente.
- Cada implementación aporta su catálogo/branding por ruta externa, aplicado por sitio, sin
  bifurcar el código genérico.
- Los Print Formats branded se instalan por sitio (no como fixtures del app) y se seleccionan vía la
  resolución de [ADR-0005](0005-resolucion-congelamiento-print-format.md).

---

## Alternativas descartadas

- **Versionar el catálogo/branding real dentro del app:** publicaría datos de cliente en un repo público.
- **Fork por cliente:** multiplicaría el mantenimiento del código genérico.

---

## Fuera de alcance

- El contenido editorial y el diseño visual concreto de cada cliente (viven en su espacio privado).
