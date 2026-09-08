# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-07
**Rama activa:** `feat/addendum-canonical-contract` (base `upstream/version-16` = v0.21.0; versión objetivo **0.22.0**)
**Tarea actual:** Contrato canónico de addendas `<ROOT>-ADD-<NN>` — implementado y validado; en ciclo `/ship`.

---

## Recuperación rápida

Estoy trabajando en:
Formalización del **contrato canónico de addendas** en `erpnext_proposals`: semántica única en
`utils/addendum.py` (reconocimiento/parseo/root, namespace reservado, resolución de Project raíz, creación
atómica), exclusión estructural de addendas del auto-Project y refuerzo de `apply_addendum_to_project`.

Plan que estoy siguiendo:
Instrucciones del usuario en la sesión (contrato aprobado punto por punto) + ADR-0019 §5–§6.

Objetivo inmediato:
Cerrar el ciclo git: `/ship commit` → (si verde) `/ship push` → (si alineado) `/ship pr` contra `version-16`.
**Detenerse antes del merge** (el merge lo hace el usuario).

Criterio de avance:
Commit con gates verdes (datos-cliente, documental, ruff, mkdocs --strict) y sin cambios inesperados;
push alineado con el mismo HEAD; PR abierto contra `version-16` con bump 0.22.0.

---

## Estado actual

### Ya cerrado
- `utils/addendum.py`: `is_addendum_group`/`parse_addendum_group`/`resolve_root_group`,
  `assert_group_not_reserved` (fail-closed), `resolve_root_project`, `create_addendum_quotation` (atómica,
  lock `FOR UPDATE` por ROOT, addenda = delta sin copiar items/scope/`proposal_project`/template).
- Guards integrados: `quotation.py` (namespace reservado en `before_insert`), `workflow_validations.py`
  (exclusión auto-Project al encolar), `project.py` (job + `create_project_from_quotation` fail-closed +
  match del Project raíz en `apply_addendum_to_project`).
- `tests/test_addendum.py` (19 tests) — verde. Suite completa 676/677.
- Docs: ADR-0019 §5–§6, CHANGELOG (`[No liberado]`), arquitectura.md. `__version__` → 0.22.0.

### En progreso
- `/ship commit` de la rama.

### Pendiente inmediato
1. Confirmar commit (mensaje `feat(proposals): contrato canónico de addendas <ROOT>-ADD-<NN> (v0.22.0)`).
2. `/ship push` si el commit queda verde.
3. `/ship pr` contra `version-16`; detenerse antes del merge.

### No repetir
- No volver a cambiar la versión (ya en 0.22.0).
- No intentar corregir `test_09b` (#60): falla **ambiental** local (`allow_multiple_items=1`), pasa en CI.
  No manipular `Selling Settings` para verde artificial.
- No tocar `pmo`. No agregar campos `addendum_of`. No crear ADR nuevo (ADR-0019 ampliado).
- La primitive NO es "calcular string y crear después": generación+insert atómicos bajo lock por ROOT.

---

## Decisiones vigentes
- `proposal_group` sigue **opaco** para el resto de la app; solo `utils/addendum.py` conoce la semántica.
- `Ganada` = aprobación comercial. Una addenda NUNCA crea Project; su alcance se incorpora al Project raíz
  **después**, por aplicación explícita gobernada por PMO (`apply_addendum_to_project`).
- Addenda-delta vacía: se inicializan totales en 0 (ERPNext hace early-return sin items y deja totales en None).
- Contrato consumible por `pmo` documentado en ADR-0019 §6 (firmas/excepciones/condición transaccional/versión).

---

## Archivos relevantes ahora

### Leer primero
- `erpnext_proposals/erpnext_proposals/utils/addendum.py` (módulo canónico)
- `docs/adr/0019-aplicar-addendum-a-project-existente.md` (§5–§6)

### Probablemente editar
- Ninguno (implementación cerrada; solo ciclo git).

### No tocar
- `pmo` (repo externo). `Selling Settings` en el site de tests.

---

## Riesgos / cuidados
- Semgrep no está instalado localmente (no modificar el ambiente sin permiso). Revisión manual conforme;
  CI lo aplica sobre el diff.
- `one_offs/scan_groups.py` es gitignored — nunca commitear.

---

## Información faltante
- Ninguna para cerrar el PR. La aplicación real desde `pmo` (creación + aplicación de addenda end-to-end)
  se ejercita en el ciclo de `pmo`, fuera de este PR.
