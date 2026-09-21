# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-21
**Rama activa:** `fix/versioning-inherit-commercial-fields` (base `upstream/version-16` = v0.25.2; objetivo **0.26.0**)
**Tarea actual:** Versionado de propuesta — herencia por defecto del estado comercial (bug de pérdida de `crm_deal` y otros).

---

## Recuperación rápida

Estoy trabajando en:
`create_new_proposal_version()` perdía `crm_deal` (rompía vínculo con Frappe CRM) y —al forzar recrear
desde CRM— también `valid_till`, impuestos, T&C, plazo contractual, financiamiento, optional sections,
payment schedule manual, contacto, direcciones. Causa: dict manual desactualizado.

Plan que estoy siguiendo:
Diseño aprobado: **inherit-by-default metadata-driven** (heredar todo campo `no_copy=0` no excluido +
FORCE_INCLUDE + TRANSFORM), con deny-lists explícitas donde `no_copy` no basta (frozen de Required/Scope
Item), y test de cobertura anti-regresión. Ver ADR-0021.

Objetivo inmediato:
`/ship` (commit+push+PR) del app; luego cortar pack 1.29.0 con el PF V2 (Versión + leyenda); luego E2E
real Deal→V1→Rechazada→V2 en QA; producción bloqueada hasta pasar E2E.

Criterio de avance:
13/13 tests nuevos; 28/28 versionado existente; suite 783/784 (#60 ambiental); mkdocs strict OK.

---

## Estado actual

### Ya cerrado (esta rama)
- `utils/proposal_versioning.py`: constructor metadata-driven (`_copy_fields`/`_copy_row` + `_EXCLUDE`/
  `_FORCE_INCLUDE`/`_SYS_EXCLUDE`/`_CHILD_TABLES` + TRANSFORM). `_resolve_new_version_payment` preserva
  schedule manual (sin throw). `valid_till` heredado literal si vigente; blanco si venció (ERPNext
  prohíbe `valid_till < transaction_date` en cada save).
- `utils/quotation_contact.py`: `set_proposal_contact` no sobrescribe contacto heredado en versionado
  (respeta `flags.from_proposal_versioning`); creación inicial Deal→Quotation intacta.
- Tests: `test_versioning_inherit_fields` (13), `test_item_proposal_fields` actualizado a `_copy_row`.
- Bump 0.26.0 + CHANGELOG + ADR-0021 + mkdocs nav.

### PF V2 (pack privado — working files, NO en este repo)
- `propuesta_servicios_profesionales__2026-09-21__v2.html/.css`: `Versión: {{ doc.proposal_version or 1 }}`
  en header; leyenda de sustitución (solo `proposal_version > 1`) bajo el header, antes del primer
  render_section. Falta cortar release **1.29.0** del pack (el 1.28.0 sellado NO incluye la leyenda).

### Pendiente inmediato
1. `/ship pr` del app (rama actual) + CI verde. Detener antes del merge (lo hace el usuario).
2. Cortar pack **1.29.0** (PF V2 + lo destinado a esa versión).
3. Instalar ambos en QA (proposals.dev) + **E2E real** Deal→V1→Rechazada→V2; verificar crm_deal,
   contacto, plazo, pagos, impuestos, vigencia, optional sections y PDF Versión:2 + leyenda.
4. Solo si pasa E2E → producción.

### No repetir
- No copy_doc puro (filtraría frozen de Required/Scope Item no marcados no_copy).
- No parche puntual de crm_deal.
- El test de cobertura meta-driven obliga a clasificar cualquier campo nuevo.

---

## Decisiones vigentes
- Heredar por defecto todo el estado comercial; excluir solo identidad/workflow/cadena/downstream/
  frozen/derivados (ADR-0021).
- `valid_till`: literal si vigente; blanco si venció; nunca inventar fecha.
- Contacto: heredado; no re-decidido por el Deal en versionado.

## Información faltante
- Ninguna para el PR. E2E real + corte pack pendientes.
