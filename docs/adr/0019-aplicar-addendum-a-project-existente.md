# ADR-0019: Contrato canónico de addendas — creación atómica y aplicación a un Project existente

**Fecha:** 2026-09-06 (§1–§4, #59) · ampliado 2026-09-07 (§5–§6, contrato canónico de addendas)
**Status:** Aceptado
**Rama:** feat/apply-addendum-to-project → version-16 (#59); feat/addendum-canonical-contract → version-16 (canónico)
**Relacionado:** reutiliza los guards de versión de [ADR-0017](0017-required-items-modelo-economico-aditivo.md)
(paquetes de alcance en `required_items`) y la generación de Project/Tasks descrita en la arquitectura; provee
el contrato que consume el **Integrated Change Control de `pmo`** (ADR-0005 de `pmo`, ciclo separado). Convive
con **#39** (handoff automático al Ganar): §5 define la **exclusión estructural** de las addendas de esa
automatización. **No** es #32 (refactor del modelo de alcance).

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

> **"Addendum" no es una entidad nueva.** Es una **Quotation** usada como modificación comercial. No hay
> DocType `Addendum` ni `Proposal`; Proposal sigue siendo Quotation. Su identidad se codifica **enteramente**
> en el `proposal_group` con el patrón reservado `<ROOT>-ADD-<NN>` (formalizado en §5): no existen campos
> `addendum_of` / `source_proposal_group`; para el resto de la app `proposal_group` sigue siendo **opaco**.

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

---

## 5. Contrato canónico de addendas (ampliación 2026-09-07)

Formaliza **qué es** una addenda, **cómo se crea de forma segura** y **cómo se comporta al Ganar**, sin nuevos
DocTypes, campos ni un segundo sistema de versionado. Toda la semántica vive en un único módulo:
`erpnext_proposals/utils/addendum.py`. El resto de la app trata `proposal_group` como clave **opaca**.

### 5.1 Namespace reservado `<ROOT>-ADD-<NN>`

- La propuesta **original** conserva su `proposal_group` (el **ROOT**). Cada **addenda** usa un grupo **nuevo**
  `ROOT-ADD-NN`; sus **revisiones/versiones** conservan exactamente ese grupo (cadena de versionado
  independiente vía `create_new_proposal_version`, sin cambios).
- `ROOT-ADD-01` y `ROOT-ADD-02` son **grupos independientes** con su propia cadena single-live.
- El sufijo `-ADD-<NN>` queda **reservado** y **fail-closed**: `on_quotation_before_insert` rechaza que una
  Quotation **nueva** introduzca manualmente un grupo que case el patrón. Solo lo permiten dos flujos
  autorizados, señalados por **flags transitorios** (no persistidos, no seteables por REST):
  `from_addendum_creation` (creación de addenda) y `from_proposal_versioning` (revisión que conserva el grupo).
  Compatibilidad histórica: verificado que **0** grupos existentes casan el patrón; no hay reinterpretación de
  datos previos.

### 5.2 Creación atómica — `create_addendum_quotation(root_quotation: str) -> str`

Una primitive que **solo calcule y devuelva** `ROOT-ADD-NN` **no** garantiza unicidad si la creación de la
Quotation ocurre después en otra transacción (dos callers leen el mismo `max(NN)` y crean grupos duplicados).
Por eso la generación de secuencia y la creación son **atómicas** en la misma transacción, con el **mismo
mecanismo nativo** que el versionado (`SELECT ... FOR UPDATE`):

1. Resuelve el `proposal_group` **root canónico** de la referencia (sube hasta el ROOT real aunque reciba una
   versión o una addenda).
2. Adquiere un lock `SELECT ... FOR UPDATE` **por el ROOT** (bloquea las filas del grupo raíz, que siempre
   existe): serializa cualquier intento concurrente del mismo root **aunque los callers pasen versiones/addendas
   distintas** del grupo. **No** es un lock por el nombre concreto recibido.
3. Calcula la siguiente secuencia `ADD-NN` con el estado bajo lock.
4. Crea la Quotation-addenda en la **misma transacción** con `proposal_group = ROOT-ADD-NN` y
   `proposal_version = 1`. **No** hace commit manual (atómico con el request del caller).

**Contenido inicial (Alternativa A — la addenda es el DELTA comercial).** Hereda solo contexto comercial seguro
(Company, Customer/party, moneda, lista de precios, centro de costo) para que sea editable normalmente. **No**
copia items originales, Scope Items originales, `proposal_project`, snapshot ni `proposal_template`: copiar el
alcance original haría que la aplicación volviera a materializar trabajo ya existente en el Project. La preventa
edita el delta (nuevo alcance) antes de someter y Ganar.

### 5.3 Resolución del Project raíz — `resolve_root_project(root_group) -> str`

Única fuente de verdad: `ROOT` → **propuesta Ganada vigente** del grupo raíz → su `proposal_project` → Project.
**Nunca** `Project.project_name`, inferencia por nombre, búsqueda fuzzy, ni un Project arbitrario provisto por
el caller.

### 5.4 Comportamiento al Ganar — clasificación central, sin duplicar workflow

Un **único** workflow y la misma transición `→ Ganada` para propuesta normal y addenda. La diferencia es el
**comportamiento posterior**, decidido por el tipo de `proposal_group`:

- **Propuesta normal Ganada:** acciones comunes (correo) + si `auto_create_project_on_won = 1`, crea/reutiliza
  Project y materializa Scope Items → Tasks (comportamiento actual, sin cambios).
- **Addenda Ganada:** acciones comunes (correo) + **NUNCA** crea Project. `auto_create_project_on_won` aplica
  **solo** a propuestas normales; **no** existe —conceptualmente— un toggle "auto-create para addenda". La
  exclusión es **estructural**, en tres capas: (a) el gate de encolado no encola; (b) el job revalida y sale;
  (c) `create_project_from_quotation` es **fail-closed** para addendas (también cubre el botón manual).
- `Ganada` = **aprobación comercial**. Una addenda **no** termina funcionalmente en `Ganada`: su alcance se
  incorpora al Project raíz **después**, mediante la **aplicación explícita** gobernada por PMO
  (`apply_addendum_to_project`). Llegar a `Ganada` **no** aplica la addenda automáticamente.

### 5.5 `apply_addendum_to_project` reforzado para addendas

Cuando la Quotation es una addenda (`is_addendum_group`), además de los guards de §2 (submitted + `Ganada` + no
superseded + single-live **de su propio grupo** `ROOT-ADD-NN` + coherencia Company/Customer + `proposal_project`):
deriva el ROOT, **resuelve** el Project raíz (§5.3) y **exige** que el `project` recibido **coincida
exactamente**. Materializa solo el alcance ejecutable **de esa addenda** sobre el Project existente (reusa
`_materialize_scope_into_project`), idempotente; asocia `proposal_project` solo tras materializar; **no** crea
Project; **no** commitea. Reaplicar la misma addenda no duplica; una addenda distinta del mismo root agrega su
propio alcance al mismo Project.

## 6. Contrato consumible por `pmo`

`pmo` **no** replica regex, parsing, secuencia ni resolución de Project; **no** crea `proposal_group` a mano ni
escribe `proposal_project`. Consume, server-side (`frappe.get_attr`, **no** whitelisted):

| Primitive | Firma | Devuelve | Excepciones | Condición transaccional | Versión mínima |
|---|---|---|---|---|---|
| Crear addenda | `create_addendum_quotation(root_quotation: str) -> str` | `name` de la nueva Quotation `ROOT-ADD-NN` (Borrador) | `frappe.throw` si falta root/permiso | **Atómica**: llamarse **dentro del request** (no encolada); generación+insert en la misma transacción bajo lock por-root | 0.22.0 |
| Aplicar addenda | `apply_addendum_to_project(quotation: str, project: str) -> dict` | resumen de materialización | `frappe.throw`/`PermissionError`; PMO propaga y NO marca aplicado | **Sin commit interno**: atómico con el request de PMO | 0.20.0 (reforzado 0.22.0) |
| Resolver Project raíz | `resolve_root_project(root_group: str) -> str` | `name` del Project raíz | `frappe.throw` si no hay Ganada vigente/Project | Solo lectura | 0.22.0 |

**Flujo PMO:** identificar Project/Change Request → solicitar `create_addendum_quotation` → gestionar sus
estados de Change Control → esperar a que la addenda quede `Ganada` → llamar `apply_addendum_to_project(quotation,
project)` → **solo tras retorno exitoso** marcar `applied_to_project`/`applied_at`/`applied_quotation` → manejar
Current Plan, baseline y cierre. Permiso de creación: `assert_can_manage_proposals` (autoría comercial,
consistente con el versionado).
