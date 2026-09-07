# ADR-0019: Aplicar una Quotation/Addendum ganada a un Project existente

**Fecha:** 2026-09-06
**Status:** Propuesto — pendiente de aprobación
**Rama:** feat/apply-addendum-to-project → version-16
**Relacionado:** reutiliza los guards de versión de [ADR-0017](0017-required-items-modelo-economico-aditivo.md)
(paquetes de alcance en `required_items`) y la generación de Project/Tasks descrita en la arquitectura; provee
el contrato que consume el **Integrated Change Control de `pmo`** (ADR-0005 de `pmo`, ciclo separado). **No**
es #39 (handoff automático al Ganar) ni #32 (refactor del modelo de alcance).

---

## 1. Contexto

El **Integrated Change Control** de `pmo` (rama `feat/change-control`) necesita gobernar cambios de alcance:
cuando un Change Request aprobado tiene una **Quotation/Addendum Ganada**, hay que **incorporar su alcance a un
Project que YA existe**, sin crear un Project nuevo. `pmo` **no** reproduce la lógica comercial de
`erpnext_proposals` ni escribe `proposal_project`: **delega** server-side (`frappe.get_attr`) en un contrato
acordado y solo fija `applied_to_project`/`applied_at`/`applied_quotation` tras un retorno exitoso.

En `erpnext_proposals` ya existía `create_project_from_quotation()`, que sabe **reutilizar** un Project cuando
`proposal_project` ya apunta a uno, pero conserva una rama que **crea** Project y exige rol
**Proposals Manager/System Manager**. Ese contrato no sirve tal cual para el addendum: (a) su promesa explícita
es "**jamás crear Project**"; (b) el ejecutor real en `pmo` es el **dueño del Project** (P4), no necesariamente
Proposals Manager; (c) debe ser **atómico** con el request externo de `pmo`.

> **"Addendum" no es una entidad nueva.** Es una **Quotation** usada como modificación comercial (otra versión
> o una Quotation de otro `proposal_group`). No hay DocType `Addendum` ni `Proposal`; Proposal sigue siendo
> Quotation.

## 2. Decisión

Se agrega un contrato **server-side** en `erpnext_proposals`:

```python
# erpnext_proposals/erpnext_proposals/utils/project.py  — NO whitelisted (a propósito)
def apply_addendum_to_project(quotation: str, project: str) -> dict
```

- **Deliberadamente NO `@frappe.whitelist()`.** `pmo` lo invoca por `frappe.get_attr` (llamada Python
  server-side), no por HTTP. No whitelistearlo minimiza la superficie pública y no anticipa necesidades de #39.
- **Separación de autoridades:**
  - **Comercial:** la Quotation `Ganada` ya sella la autoridad comercial. Se valida reutilizando
    `assert_can_create_project()` (submitted + `Ganada` + no `superseded` + single-live del `proposal_group`).
    **No** se exige Proposals Manager: esa autoridad ya quedó ejercida al llevar la propuesta a `Ganada`.
  - **Operacional:** incorporar alcance al *Current Plan* de un Project es autoridad **operacional** =
    permiso `write` efectivo sobre el Project destino (`project_doc.check_permission("write")`). Con `pmo`
    instalado, sus hooks **P4** vuelven ese `write` **owner-only**, **sin** que `erpnext_proposals` importe ni
    dependa de `pmo`. Sin `pmo`, aplican los permisos estándar de Project. **No** se usa `ignore_permissions`
    como autorización del endpoint.
- **Garantía estructural "nunca crea Project":** se extrae una **primitive** de materialización que opera sobre
  un **Project ya resuelto** y **no** tiene rama de creación:

  ```
  _validate_scope_for_project(quotation) -> exec_rows      # preflight: Template + filas ejecutables + fase
  _materialize_scope_into_project(quotation, project, exec_rows) -> dict   # Tasks; NO crea Project; NO commit
  ```

  - `create_project_from_quotation()` conserva su **comportamiento público**: auth PM → `assert_can_create_project`
    → preflight → `_resolve_project_type` → **resolver/reutilizar/crear** Project → primitive → `frappe.db.commit()`.
  - `apply_addendum_to_project()` → `write` sobre Project + `assert_can_create_project` + preflight + coherencia
    → **primitive** sobre el Project existente → asociar `proposal_project`. **Sin rama de creación.**
- **Preflight antes de efectos secundarios:** Template/filas ejecutables/fase se validan **antes** de tocar
  Project o Tasks (evita dejar estado a medias por un preflight fallido).
- **Idempotencia:** las Tasks hijas se deduplican por `(project, source_quotation_scope_item)` (el `name` del
  child `Quotation Scope Item`, único por ocurrencia); las Task-fase se reutilizan por `(project, proposal_phase)`.
  Como dos Quotations distintas producen `Quotation Scope Item` distintos, un Addendum **agrega** sus Tasks sin
  colisionar con las originales; reejecutar el mismo Addendum **no** duplica.
- **`proposal_project` es administrado exclusivamente por `erpnext_proposals`** (Link read-only, `allow_on_submit`).
  El addendum lo asocia **después** de una materialización exitosa (validando: vacío → asocia; == target →
  idempotente; ≠ target → error). `pmo` nunca lo escribe.
- **Sin `frappe.db.commit()` en el path del Addendum.** La primitive no commitea; `apply_addendum_to_project`
  tampoco. Así el flujo es **atómico** con el request externo de `pmo`
  (`helper → materializa → retorna → pmo fija applied_* → save → commit del request`): si algo falla, el
  rollback externo revierte Tasks y asociación juntas; si el helper falla, `pmo` **no** marca el CR aplicado.
- **`create_project_from_quotation()` conserva por ahora su `frappe.db.commit()`** y comportamiento existente
  (su único caller productivo es el botón de la Quotation). Eliminar ese commit sería un refactor independiente,
  fuera de #59.

### Project Type: asimetría deliberada (no es un olvido)

`apply_addendum_to_project()` **no** llama `_resolve_project_type()`, **no** valida compatibilidad de Project
Type y **no** modifica `Project.project_type`.

**Fundamento:** `proposal_project_type` (ADR-0017) es metadata que **inicializa `Project.project_type` al
CREAR** un Project. El bloqueo de **≥2 tipos distintos** existe únicamente para no elegir arbitrariamente un
único tipo para un Project **nuevo** (evitar *last-wins*); **no** significa que la Quotation sea intrínsecamente
inválida, ni establece una regla de **homogeneidad metodológica** para cambios posteriores. La materialización
de Tasks nunca lee `project_type`.

Consecuencias explícitas (aceptadas):

- un Addendum **Agile** puede incorporarse a un Project cuyo `project_type` es **Cascada**;
- un Addendum con paquetes que declaren **tipos distintos** también puede incorporarse;
- el *Current Plan* **conserva** el `project_type` ya existente;
- **no** se inventa una invariante nueva.

Por eso la asimetría con `create_project_from_quotation()` (que sí bloquea ≥2) es **intencional**: crear necesita
resolver UN tipo; aplicar alcance a un Project ya tipado **no** resuelve ni cambia el tipo.

### Disparo explícito

Llegar a `Ganada` **no** dispara automáticamente la aplicación al Project. La incorporación es una acción
**explícita** (la ejecuta `pmo` desde el Change Request aprobado, o un caller server-side equivalente). La
automatización amplia al Ganar es **#39** y se mantiene separada.

## 3. Consecuencias

- `pmo` puede gobernar cambios de alcance sin duplicar lógica comercial ni crear Projects nuevos; la frontera
  entre apps queda en un único contrato nombrado.
- La materialización de Tasks queda **componible** (primitive sin commit) y reutilizable por futuros callers
  (p. ej. #39 podría reutilizar la misma primitive sin fusionar su alcance con #59).
- `create_project_from_quotation()` no cambia de comportamiento observable (mismos guards, mismo commit, mismos
  tests).
- Deuda menor conocida: en el Addendum, `_resolve_native_dependencies` resuelve dependencias solo entre las
  filas de la propia Quotation aplicada (una dependencia hacia un scope que solo existe en otra Quotation queda
  no-resuelta, contada, sin error).

## 4. Alternativas descartadas

- **Wrapper que pre-setea `proposal_project` y llama `create_project_from_quotation()`**: deja **físicamente
  viva** la rama de creación de Project; garantía "nunca crea" solo **blanda**. Descartada a favor de la
  primitive (garantía **estructural**).
- **Exigir Proposals Manager en el Addendum** (por simetría con `create`): rompería el modelo **owner-only** de
  `pmo`; la autoridad comercial ya está sellada por `Ganada`. Descartada.
- **Whitelistear el helper**: innecesario (llamada server-side por `get_attr`); aumenta superficie. Descartada.
- **Validar/bloquear Project Type en el Addendum** (opciones B/C del análisis): malinterpreta la semántica de
  `proposal_project_type` (creación-only) o inventa una invariante de homogeneidad inexistente. Descartada.
