# ADR-0023: Depuración de fuentes de verdad — el pack privado deja de distribuir maestros funcionales

**Fecha:** 2026-09-22
**Status:** Cerrado — vigente. Contrato de alcance del loader de catálogos (caps v12).
**Rama:** refactor/loader-drop-desk-managed-seeders → version-16

---

## Contexto

El loader de catálogos (`catalog_data/catalog_loader.py`) sembraba, desde un archivo JSON externo
(pack privado por implementación/cliente), tanto la capa **editorial/de presentación** como una amplia
capa de **maestros funcionales**: Proposal Templates y su estructura, Scope Items y sus relaciones,
Proposal Phases y sus Tags nativos, el registro/flags funcionales de Item (`item_name`, `item_group`,
`stock_uom`, `is_stock_item`, `is_sales_item`, `is_purchase_item`), Payment Terms / Payment Terms
Templates, Designations, Skills y `economic_behavior_rules`.

Esos maestros son datos que los usuarios administran naturalmente desde ERPNext/Frappe (Desk). Tenerlos
también en el pack convertía al pack en una **segunda fuente de verdad**: el loader podía crear,
actualizar, comparar y generar **conflictos** sobre datos ya gobernados en Desk (canal `conflicts` real,
riesgo de divergencia y de sobre-escritura con `update_content`). Tras la materialización de la propuesta
en la Quotation ([ADR-0022](0022-materializacion-secciones-quotation.md)), los documentos formales ya no
dependen de leer estos maestros en vivo, lo que dejó sin justificación la distribución de esos maestros
por archivo.

## Decisión

El pack privado **deja de distribuir los maestros funcionales**; se administran **EXCLUSIVAMENTE en
Desk**. El loader se depura para conservar **solo la capa editorial/de presentación**:

- Proposal **Sections** (contenido narrativo);
- **contenido editorial de Items** (methodology / expected result / scope limit / service text /
  validity / min unit / service hours). **El loader NUNCA crea Items**: el registro/flags funcionales se
  crean y administran en Desk; si el Item no existe, se reporta en `pending` y se omite;
- **Letter Heads**;
- **Print Formats** y su **versionamiento declarativo** (deshabilitar el anterior + adjuntar changelog).
  El versionamiento **ya no repunta Proposal Templates** (los catálogos dejan de declarar `templates` en
  `print_format_versions`); ese repunte lo decide un usuario en Desk;
- **`clear_fields`** limitado a tipos editoriales (`sections`, `items`, `letter_heads`).

Se **retiran** los seeders de los maestros funcionales y toda lógica que quedaba muerta como
consecuencia (validaciones, conflictos, remaps y dependencias asociadas). `capabilities()` deja de
exponer `designations_skills`, `phase_tags`, `payment_terms`, `economic_behavior_rules` y
`scope_pmo_planning`, y **añade** la garantía `no_functional_master_writes` (verificada por ausencia de
esos seeders). **`LOADER_CAPS_VERSION` sube a 12.**

**Contrato con el instalador del pack:** una vez que estos datos salen del pack, el loader **no vuelve a
crearlos, actualizarlos, compararlos ni generar conflictos** sobre ellos. El instalador
(`install_or_update_proposals.sh`) exige `MIN_CAPS_VERSION=12` y `REQUIRED_CAPS =
no_functional_master_writes print_formats print_format_versions letter_heads clear_fields`.

No se introduce ningún mecanismo alternativo de migración ni una nueva fuente de verdad. **No se borra
ningún dato existente de la base de datos**: la depuración solo retira la distribución por archivo; los
registros ya presentes en cada site permanecen y se administran en Desk.

## Consecuencias

- **Una sola fuente de verdad** para los maestros funcionales (Desk). Desaparece el riesgo de divergencia
  y de conflictos del loader sobre datos gobernados en Desk.
- El pack se vuelve **puramente editorial/de presentación**; su versión mayor sube a `2.0.0` en los packs
  reales para señalar el cambio de contrato.
- **Alta inicial en un site nuevo:** los Items (y demás maestros) deben existir en Desk **antes** de
  aplicar el pack; el loader solo actualiza el **contenido editorial** de Items existentes.
- Se retiran las capacidades y tests que ejercían los seeders eliminados; los tests del loader se
  re-basan en la capa editorial y **fijan por regresión** la ausencia de los seeders retirados
  (`no_functional_master_writes`, allowlist).
- El versionamiento de Print Formats ([ADR-0011](0011-candado-print-formats-historicos.md) sigue vigente)
  conserva *deshabilitar anterior* + *changelog*; el repunte de plantillas pasa a Desk.

## Alternativa descartada

**Mantener los maestros en el pack marcándolos "solo lectura"/no-update.** Descartada: seguiría habiendo
dos definiciones del mismo dato (archivo y Desk), el canal `conflicts` seguiría activo y el pack seguiría
siendo una fuente de verdad paralela. La separación limpia (editorial en el pack, funcional en Desk) es
la única que elimina la divergencia de raíz.

## Deuda futura (alcance NO cerrado en esta decisión)

La extracción se **detuvo deliberadamente** en la capa editorial. **Se quedan en el pack, por ahora,
como deuda futura reconocida:**

- **`Proposal Section.content`** (y los atributos del propio registro Proposal Section: `title`,
  `is_executive_summary`, `enabled`);
- **contenido editorial de Items** (`description`, `proposal_methodology`, `proposal_expected_result`,
  `proposal_scope_limit`, `proposal_service_validity`, `proposal_min_unit`, `proposal_service_hours`).

**Motivo:** no existe todavía una alternativa satisfactoria para administrar **contenido dinámico**
(narrativa/editorial) desde Desk sin perder versionamiento, reutilización ni el flujo de materialización
en la Quotation ([ADR-0022](0022-materializacion-secciones-quotation.md)). Desmontar parcialmente estas
piezas sin esa alternativa no aporta valor y sí riesgo. Por eso siguen distribuyéndose por el pack (que
quedó reducido a **presentación + contenido editorial**).

**Verificación (auditoría read-only del pack activo v2.0.0):** el catálogo raíz —lo único que carga el
loader— contiene **solo** `sections`, `items` (editorial), `print_formats`, `print_format_versions`,
`letter_heads` y `versioned`; **ningún** maestro funcional (Templates/Scope Items/Phases/Payment
Terms/Designations/Skills/`economic_behavior_rules`) ni campo de registro/flags de Item. El dato funcional
histórico sobrevive únicamente **fuera de la ruta de carga** (snapshots `releases/<pre-2.0.0>` inmutables
y `sources/*.xlsx`), con el normalizer del pack ya neutralizado.

**Pendiente de decisión futura (no en este bloque):** cómo y cuándo administrar `Proposal Section.content`
y el contenido editorial de Items desde una fuente única sin sacrificar contenido dinámico. Hasta
resolverlo, permanecen en el pack.
