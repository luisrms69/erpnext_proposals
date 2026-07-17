# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-07-17
**Rama activa:** `feat/proposal-project-task-integration` (pusheada a `upstream`, historia saneada)
**Tarea actual:** PR #31 abierto a `version-16`. CI marcó `frappe-security-file-traversal` en el loader → fix `# nosemgrep` (comment-only). Siguiente: `/ship push` del fix; el CI del PR re-corre.

---

## Recuperación rápida

Estoy trabajando en:
Cierre de `erpnext_proposals`. El app genérico queda documentado (resolución/congelamiento de Print
Format y separación entre app genérica y personalización privada por cliente). Los Print Formats
branded, catálogos reales y assets del cliente son **datos privados que viven fuera del repo** y se
aplican por site.

Plan que estoy siguiendo:
Ciclo de cierre: documentación → `/ship commit` (hecho) → `/ship push` → PR a `version-16`
(cada paso con autorización explícita por separado).

Objetivo inmediato:
`/ship push` de la rama, ya con la historia saneada de contenido específico de cliente.

Criterio de avance:
Ningún objeto publicado debe contener datos de cliente.

---

## Estado actual

### Ya cerrado
- Resolución + congelamiento del Print Format comercial (override → Proposal Template → default;
  efectivo congelado al pasar a En Revisión) — ADR-0005.
- Loader genérico de catálogos por ruta externa y separación app-genérica vs personalización privada
  por cliente — ADR-0006.
- Documentación actualizada (`tecnico/print-formats.md`, `tecnico/arquitectura.md`,
  `usuario/generar-enviar-propuesta.md`, ADR-0005, ADR-0006, CHANGELOG, mkdocs nav).
  `mkdocs build --strict` limpio. Suite automática 167 OK.

### Pendiente inmediato
1. `/ship push` del fix `# nosemgrep` (requiere autorización).
2. `/ship pr` a `version-16` sin repetir toda la batería (pr-ready ya corrido: ruff/tests/mkdocs verdes).
3. Esperar CI → merge (lo hace el usuario) → `/sync-check`.

### No repetir
- No versionar contenido de cliente (branding, catálogos reales, assets, one_offs, PDFs).
  [[feedback_no_crear_transaccionales_de_prueba]]
- No `git` manual — solo vía `/ship`. [[feedback_git_solo_via_ship]]
- **NUNCA** merge — lo hace el usuario. [[feedback_nunca_merge]]

---

## Decisiones vigentes
- Print Format comercial: cadena override → Proposal Template → default; congelamiento del efectivo
  al pasar a En Revisión (ADR-0005).
- App genérica en el repo; catálogos/branding/assets reales fuera del repo, aplicados por site (ADR-0006).

---

## Archivos relevantes ahora

### Leer primero
- `docs/tecnico/print-formats.md`, `docs/adr/0005-*.md`, `docs/adr/0006-*.md`

### No tocar
- Datos de los sites de prueba (no borrar/limpiar). Propuestas congeladas.

---

## Riesgos / cuidados
- `one_offs/` no está en `.gitignore`; el flujo `/ship` los excluye, pero nunca usar `git add -A`.

---

## Información faltante
- Definición del usuario sobre pasos posteriores del cierre.
