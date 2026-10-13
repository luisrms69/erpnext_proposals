# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-10-11
**Rama activa:** `feat/simplify-procurement` (base `upstream/version-16` = v0.35.0 → objetivo **v0.36.0**, MINOR)
**Tarea actual:** Eliminar el abastecimiento modelado en la propuesta (ADR-0026) — la compra va a Buying nativo.

---

## Recuperación rápida

Se eliminan los tres mecanismos de compra superpuestos en la propuesta: **paquete de Gestión de Compras**
(`default_procurement_package_item`, #55) + su autoload, **Scope de compra por obligación**
(`default_purchase_scope_item`, #79) + la Task «Comprar — …» por ocurrencia, y el **bloqueo `sin_compra`**
(`assert_program_prerequisites`). También se retira el Custom Field `Item.proposal_skip_procurement`. El
alcance de cada ocurrencia pasa a ser **solo su Scope propio** (N:M): un Item comprable vendido sin Scope
genera su **Task operativa «Entregar»** (ADR-0025), no una Task de compra. Desbloquea ganar propuestas de
puro licenciamiento (SAL-QTN-2026-00024) sin configurar nada. El **costo de compra** en Rentabilidad
Estimada (pricing nativo por `is_purchase_item`) no cambia. Ver ADR-0026.

---

## Estado actual

### Hecho (en dev)
- Código: `utils/quotation.py` (retiro de `_autoload_procurement_package`, `_applicable_purchasables`,
  `_is_applicable_purchasable_code`, `_append_fallback_scope`, `assert_program_prerequisites` y la rama de
  compra de `_append_scope_rows_for_row`), `utils/project.py` (`_scope_task_subject` sin rama «Comprar»;
  sin `_purchase_code`/`_settings`), `utils/workflow_validations.py` (sin el prerrequisito `sin_compra`).
- Fixtures/DocType: `proposal_settings.json` sin `default_procurement_package_item`/`default_purchase_scope_item`
  ni `procurement_section`; `custom_field.json` + `hooks.py` sin `proposal_skip_procurement`.
- Tests reescritos: `test_scope_fallbacks.py` (modelo sin fallbacks), `test_required_items_autoload.py`
  (solo autoload de Required Items), `test_required_items.py` (test_21 vía scope propio del Required Item).
  Regresión añadida en `test_auto_project_on_won.py` (`test_4c`): comprable sin config → Ganada + Task
  «Entregar», sin bloqueo `sin_compra` (criterio SAL-QTN-2026-00024 a nivel transición).
- **Suite completa: 812 OK (1 skip)** sobre `test-erpnext_proposals.localhost` migrado; ruff limpio.
- ADR-0026 + CHANGELOG + mkdocs nav + bump `0.35.0 → 0.36.0`; `mkdocs build --strict` OK.
- Docs de usuario/técnicas actualizadas (items-requeridos, proyecto-generado, arquitectura, doctypes).

### Pendiente inmediato
1. **Revisión del diff por el usuario** (no autorizado push/PR/merge/release/deploy todavía).
2. `/ship pr` → push y PR a `version-16` con el bump `0.36.0` ya incluido.
3. **CI** valida instalación limpia (`install-app` en sitio nuevo) + suite. **El merge lo hace el usuario.**
4. Tras merge: `/sync-check` + `/ship release` (tag/Release v0.36.0) + limpieza de rama.
5. **No desplegar** en staging ni producción todavía.

## Decisiones vigentes
- Abastecimiento fuera de la propuesta (ADR-0026). Se conservan: Task padre/operativa por Item (ADR-0025),
  Scope Items reales, paquetes de alcance N:M (ADR-0016), Required Items + autoload, inferencia de Project
  Type, costo externo nativo (ADR-0017/0024).
- Sin patch, sin SQL: campos retirados dejan columnas huérfanas inertes; `proposal_skip_procurement`
  persiste en BD de sites existentes (fixtures no borran). Forward-only; históricos intactos.
- Instalación limpia se valida por CI.

## Información faltante / riesgos
- Precaución verificada antes de implementar: en los sitios de desarrollo no hay Tasks de compra
  generadas dependientes de estos mecanismos que se vean afectadas por el cambio (forward-only).
- Coexistencia (aceptada) de propuestas históricas que usaron compra con el nuevo modelo; no se migran.
