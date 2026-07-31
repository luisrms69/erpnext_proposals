# ADR-0009 — Resolución y persistencia del contacto dirigido de la Quotation

**Estado:** Aceptado · **Fecha:** 2026-07-30

## Contexto

Las Quotations comerciales suelen **originarse desde un CRM Deal** (Frappe CRM) y luego reorientarse
al **Customer** correspondiente. La propuesta pertenece al Customer, pero está **dirigida al contacto
con quien se lleva el Deal**. En el flujo real, el prefill que el CRM arma para la Quotation y el
*fetch* nativo de ERPNext al fijar el Customer **no persisten** de forma confiable ese contacto: la
Quotation quedaba con `contact_person` vacío y `contact_display` en blanco.

El efecto observable es que el PDF de propuesta (que usa `doc.contact_display`) mostraba el **nombre de
la empresa** (`customer_name`/`party_name`) en lugar de la **persona**. Además, había Quotations Draft
ya existentes con el mismo defecto, que debían corregirse **sin** patches, backfills manuales,
`bench execute`, escrituras directas a BD ni código específico por sitio/cliente.

## Decisión

Se implementa la resolución y persistencia del contacto **exclusivamente en `erpnext_proposals`**
(`erpnext_proposals/utils/quotation_contact.py`), dentro del ciclo normal del documento, con dos
enganches sobre la misma resolución (Deal → Customer) y distinto grado de autoridad:

- **`Quotation.before_insert` → `set_proposal_contact` (autoritativo en la creación):** si la Quotation
  proviene de un Deal con contacto válido, ese contacto **gana** aunque el prefill del CRM o el *fetch*
  nativo hayan puesto otro/nada. Sin contacto del Deal, se hace *fallback* al contacto por defecto del
  Customer (`get_default_contact`).
- **`Quotation.validate` → `autocorrect_missing_contact` (autocorrección):** se aplica **solo** cuando
  `docstatus == 0`, `quotation_to == "Customer"` y `contact_person` está **vacío**. Rellena el contacto
  (Deal; si no, Customer). Si `contact_person` **ya tiene valor**, **no lo sobrescribe** (protege una
  selección manual). Así, un Draft antiguo sin contacto se corrige **solo al guardarse**, en el flujo
  normal, sin intervención externa. Los documentos Submitted/frozen (`docstatus != 0`) no se tocan.

Reglas de resolución:

- La lectura del Deal es **desacoplada del app `crm`**: `_deal_primary_contact` consulta por `frappe.db`
  y **solo** si el DocType `CRM Deal` existe (guardado por `frappe.db.exists`). Prioridad interna: fila
  de `CRM Deal.contacts` con `is_primary = 1` → campo `CRM Deal.contact` → primera fila; el candidato se
  descarta si no existe como `Contact`.
- Los derivados (`contact_display`/`contact_email`/`contact_mobile`/…) se pueblan con el nativo
  `get_contact_details`; el Print Format sigue usando `doc.contact_display` sin lógica especial.
- **Idempotente**: `validate` solo actúa con `contact_person` vacío → re-guardar no produce cambios;
  `before_insert` corre una única vez (creación).
- **Genérico**: sin código específico para un sitio, cliente, Deal, Quotation o Contact.

## Consecuencias

- Las Quotations originadas desde un Deal quedan dirigidas al contacto correcto desde su creación; el
  PDF muestra la **persona** y no la empresa.
- Los Drafts existentes con `contact_person` vacío se **autocorrigen** al pasar por su ciclo normal de
  guardado, sin patch ni operación manual.
- Se respeta la validación nativa de ERPNext: el `contact_person` fijado debe pertenecer al Customer
  (en el flujo real, el contacto del Deal es un `Contact` ligado al Customer).
- La cobertura de la rama del Deal se prueba con **mocking/stubbing** (el site de tests no tiene el app
  `crm`): precedencia Deal → Customer, *fallback* y prioridad interna de `_deal_primary_contact`.

## Alternativas descartadas

- **Patch / `after_migrate` / backfill ejecutado manualmente / `bench execute` / escritura directa a
  BD**: descartadas — la regla del proyecto prohíbe patches salvo imposibilidad absoluta, y aquí la
  autocorrección en el ciclo normal del documento resuelve el caso sin ellos.
- **Corrección de dato puntual** (para una Quotation/cliente específico): descartada — no resuelve el
  problema estructural del flujo Deal → Customer y viola la exigencia de una solución genérica.
- **Lógica de contacto en el Print Format**: descartada — el Print Format debe permanecer como
  presentación (`doc.contact_display`); la resolución pertenece al ciclo del documento.
- **Sobrescribir siempre en `validate`**: descartada — pisaría selecciones manuales; por eso la
  autocorrección es *solo-si-vacío* y el Deal solo es autoritativo en `before_insert`.
