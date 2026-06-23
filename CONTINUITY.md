# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-06-22
**Rama activa:** `feature/deploy-produccion`
**Tarea actual:** Preparar primer despliegue a producción (staging primero) + arreglar el landing del Workspace.

---

## Recuperación rápida

Estoy trabajando en:
Cambios para el primer despliegue de la app a un site nuevo: HRMS como dependencia
requerida, instalación automática del Desktop Icon, render correcto del Workspace, y la
guía de despliegue a producción.

Plan que estoy siguiendo:
Despliegue staging → producción documentado en `docs/tecnico/despliegue-produccion.md`.

Objetivo inmediato:
Commit de la rama `feature/deploy-produccion` (en curso). Luego push, PR a `version-16` y
validar en el site de staging real.

Criterio de avance:
El icono de la app abre el Workspace de tarjetas (no salta a Quotation); los Print Formats
aparecen en el selector; el checklist de `despliegue-produccion.md` corre limpio en staging.

---

## Estado actual

### Ya cerrado
- `required_apps = ["erpnext", "hrms"]` (hooks.py).
- Desktop Icon automático en `after_install` (install.py `_sync_desktop_icons`).
- Workspace `content` poblado con header + 4 cards → render correcto (validado en proposals.dev).
- Sidebar con item "Inicio" → Workspace.
- Guía `docs/tecnico/despliegue-produccion.md` + setup.md (HRMS requerido) + nota en guía de usuario + mkdocs nav + CLAUDE.md.

### En progreso
- Commit de la rama (este turno).

### Pendiente inmediato
1. Push de la rama (requiere autorización aparte).
2. PR a `version-16` (requiere autorización; correr `/pr-ready`).
3. Validar el checklist de despliegue en el site de staging real.
4. Definir `pdf_generator` de los Print Formats (workstream aparte del usuario).

### No repetir
- **NUNCA** `frappe.reload_doc(..., "workspace", ..., force=True)` con `developer_mode=1`:
  borra el `.json` fuente del Workspace (after_delete→delete_folder→rmtree; el re-export se
  suprime por `in_import`). Para cambios de workspace: editar el JSON, subir su `modified`,
  y `bench migrate`. Documentado en skill `frappe-conventions`.
- No usar `cur_frm` en JS — Frappe v16 lo deprecó.
- Remote es `upstream` (no `origin`).
- No commitear en `version-16` directamente.
- `docs/referencia/` es generada — no editar manualmente.
- Tests Frappe con `bench run-tests`, no `pytest` directo.

---

## Decisiones vigentes
- HRMS es dependencia **requerida** (no opcional) — fuente salarial de la matriz de costos.
- El Workspace se gobierna por `content` (cards), no por `links`; `links` es inerte sin un
  bloque `card` que lo referencie por `card_name`.
- `pdf_generator` de los Print Formats no está fijado en el JSON — pendiente de definir.
- Estado "Ganada" es workflow state real; botón "Crear Proyecto" requiere docstatus=1 Y workflow_state="Ganada".
- `frappe-multisite --docs erpnext_proposals` disponible en puerto 8767.

---

## Archivos relevantes ahora

### Leer primero
- `docs/tecnico/despliegue-produccion.md` — metodología y checklist de despliegue.

### Probablemente editar
- `erpnext_proposals/erpnext_proposals/print_format/*/*.json` — fijar `pdf_generator` (pendiente).

### No tocar
- El Workspace JSON vía `reload_doc force` (ver "No repetir").
- `docs/referencia/` — generado.
- `version-16` directamente.

---

## Riesgos / cuidados
- En `developer_mode`, recargar workspaces solo con `migrate` (subiendo `modified`), nunca `reload_doc force`.
- `migrate` escribe en BD — correr siempre con `--site`.

---

## Información faltante
- Nombre/host del site de staging real (no está en este bench; es servidor aparte).
- Generador de PDF correcto (`wkhtmltopdf` vs `chrome`) para los Print Formats.
