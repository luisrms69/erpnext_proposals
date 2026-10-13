# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-10-13
**Rama activa:** `fix/project-handoff-feedback` (base `upstream/version-16` = v0.36.0 → objetivo **v0.36.1**, PATCH)
**Tarea actual:** Correcciones de UX/handoff del Project detectadas en staging tras v0.36.0 (ADR-0026).

---

## Recuperación rápida

Cuatro detalles observados en staging al ganar una propuesta de puro licenciamiento (0 Scope Items) y
generar su Project (PROJ-0091 / SAL-QTN-2026-00024). Correcciones (sin colores — decisión aparte — y sin
cambiar la fecha del Project):

1. **Aviso de creación (async):** el job post-commit emite `publish_realtime("erpnext_proposals_project_created")`
   dirigido al usuario, solo tras crear realmente el Project; el form lo escucha (binding único por `window`,
   filtrado por `cur_frm`) y muestra aviso con nombre + enlace.
2. **Navegación (regresión v0.36.0):** botón «Ver Proyecto» ya no gateado por `quotation_scope_items > 0`;
   visible siempre que exista `proposal_project` (funciona con 0 QSI).
3. **Nombre del Project:** `create_project_from_quotation` retorna `project_name`; aviso/botón/indicador
   muestran el nombre, no solo `PROJ-####`.
4. **Fecha de inicio de Tasks operativas:** la Task «Entregar» hereda `Project.expected_start_date` (sin fin;
   idempotente, no sobrescribe). PMO v0.23.0 ya reporta la ausencia de fin; no se duplica.

## Estado actual

### Hecho (en dev)
- `utils/project.py`: retorno con `project_name`; `publish_realtime` en el job async; Task operativa con
  `exp_start_date` = ancla del Project.
- `public/js/quotation.js`: listener realtime único + `show_project_link` (botón «Ver Proyecto: {nombre}» +
  indicador) con 0 QSI; `_projectStates` conservado (contrato JS↔Python); `msgprint` con nombre.
- Tests nuevos: `test_scope_fallbacks.test_09/test_10`, `test_auto_project_on_won.test_4d`.
- **Suite completa: 815 OK (1 skip)**; comprobaciones JS (prettier --check, node --check) + contrato JS verdes.
- Bump `0.36.0 → 0.36.1`; CHANGELOG + CONTINUITY.

### Pendiente inmediato
1. `/ship pr` → push + PR a `version-16` con el bump 0.36.1 incluido (autorizado).
2. **CI** valida. **El merge lo hace el usuario** tras CI verde.
3. Tras merge: `/sync-check` + `/ship release` (tag/Release v0.36.1) — **sujeto a autorización posterior**.
4. **No desplegar** sin autorización.

## Decisiones vigentes
- Colores de Tasks padre: **pendiente, decisión separada** (fuera de este PR).
- Fecha del Project: origen intacto (ancla = fecha de la Cotización); solo las Tasks operativas heredan inicio.
- PMO no se modifica: su mecanismo de fechas incompletas (Project Control → Estado) es suficiente.

## Información faltante / riesgos
- El comportamiento realtime se validó por código + test (monkeypatch del evento); la recepción en vivo en
  el navegador es verificación manual de QA.
