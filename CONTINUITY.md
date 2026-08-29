# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-08-29
**Rama activa:** `docs/adr-0015-renderer-pdf` (base `upstream/version-16` = **v0.10.0**)
**Tarea actual:** Cerrar por `/ship` la **implementación base del renderer desacoplado (ADR-0015)**: capacidad genérica para que un Print Format renderice vía Gotenberg, conservando wkhtmltopdf por defecto. Commit + push hechos; **PR abierto** contra `version-16`.

---

## Recuperación rápida

Estoy trabajando en:
La capa genérica mínima ADR-0015: un Print Format elige su motor HTML→PDF con un renderer profile
técnico (`Print Format.proposal_renderer_profile`, oculto/read-only): `legacy` (wkhtmltopdf, default)
o `gotenberg-v1` (Gotenberg). Backward-compatible; ningún formato adopta `gotenberg-v1` todavía.

Plan que estoy siguiendo:
Flujo `/ship`: commit ✓ → push ✓ → **pr (PR abierto)**. Bump `__version__` → v0.11.0 ✓.
PR base `version-16`.

Objetivo inmediato:
Revisión del PR (CodeRabbit / CI). El **merge lo hace el usuario** (Squash and Merge). Tras el merge:
`/sync-check` → `/ship release` (tag + GitHub Release v0.11.0).

Criterio de avance:
CI verde en el PR; gates de `/pr-ready` pasados (355 tests OK, mkdocs --strict, ruff, versionado MINOR).

---

## Estado actual

### Ya cerrado
- Base del renderer implementada y verificada: adapter `GotenbergClient` (html_to_pdf + merge por
  endpoint, fail-closed, sin fallback), orquestación 2-render + merge en Gotenberg (pypdf fuera del
  camino contractual), inline de assets data-URI, extracción header/footer.
- Custom Field técnico `proposal_renderer_profile` (hidden/read-only) creado en `proposals-acti.dev`
  (migrate hecho) y en el site de tests. `arquitectura.md` actualizado (integración Gotenberg).
- Candado ADR-0011 extendido: `proposal_renderer_profile` inmutable en formatos históricos.
- E2E real del dispatch verificado (objetos sintéticos `_GOTENBERG-E2E-*`, creados y eliminados):
  gotenberg-v1 elegido, 2 renders + merge Gotenberg, sin get_pdf/pypdf/fallback, 4 páginas.
- ADR-0015 redactado y aprobado (Status: "base implementada; sin formatos adoptándola aún").

### En progreso
- PR abierto contra `version-16` (rama `docs/adr-0015-renderer-pdf`, 2 commits + este de CONTINUITY).

### Pendiente inmediato
1. Revisión del PR (CodeRabbit / CI verde).
2. Merge por el usuario (Squash and Merge) — Claude NO mergea.
3. Post-merge: `/sync-check` → `/ship release` (tag + GitHub Release v0.11.0).

### No repetir
- No re-diagnosticar el incidente de PDF en staging: NO es premisa del ADR (causa raíz = diagnóstico
  separado). ADR-0015 lo trata como contexto, no como causa.
- No tocar el pack Actiglobal, formatos productivos, staging ni producción en esta fase.
- No adoptar `gotenberg-v1` en ningún Print Format todavía (eso es fase de adopción, futura).
- `bench console` NO corre desde el bench root: usar rutas absolutas al `exec(open(...))`.

---

## Decisiones vigentes
- `proposal_renderer_profile` es **metadata técnica**, no control de usuario: oculto + read-only; lo
  asigna el app/loader programáticamente (hidden/read-only no bloquean escritura de servidor).
- Gotenberg pineado por versión (`gotenberg/gotenberg:8.34.0` probado); endpoint por
  `proposal_gotenberg_url` (config de entorno, no de cliente). Fail-closed sin fallback silencioso.
- Merge contractual DENTRO de Gotenberg (`/forms/pdfengines/merge`); pypdf fuera del camino.
- `docs/tecnico/print-formats.md` se actualizará en la **fase de adopción** de un formato real, no ahora.

---

## Archivos relevantes ahora

### Leer primero
- `docs/adr/0015-renderer-pdf-desacoplado-versionado.md` — decisión, frontera, hardening parqueado.

### Probablemente editar
- `erpnext_proposals/__init__.py` — bump a v0.11.0 antes de `/ship pr`.

### No tocar
- `one_offs/` (ignorado; scripts del e2e/probe temporales).
- Pack Actiglobal / formatos productivos.

---

## Riesgos / cuidados
- El ajuste visual fino de márgenes header/footer para gotenberg-v1 es actividad de **adopción (v2)**
  por formato, no de este MVP.
- Reproducibilidad: ADR-0015 garantiza HTML→PDF, **no** datos→HTML (parqueado).

---

## Información faltante
- Ninguna para continuar el `/ship`.
