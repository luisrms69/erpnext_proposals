# TASK 6 — IMPLEMENTATION_PLAN — Selección, resolución y congelamiento de Print Format

**Rama:** `feat/proposal-project-task-integration` (continúa el mismo flujo; historia se limpia pre-push).
Documento genérico (sin datos de cliente). Baseline: ver `BASELINE.md`.

## Decisiones (aprobadas por el usuario)

- **Rama:** seguir en `feat/proposal-project-task-integration` (TASK 6 integra con el congelamiento ya hecho).
- **Modelo de resolución (rutas A y B usan el MISMO resolver):**
  ```
  Propuesta congelada  → proposal_effective_print_format
  Propuesta en Borrador → proposal_print_format → Proposal Template.print_format → DEFAULT_COMMERCIAL_PRINT_FORMAT
  ```
- `Quotation.proposal_print_format` = override editable en Borrador.
- `Proposal Template.print_format` = default de la familia.
- `DEFAULT_COMMERCIAL_PRINT_FORMAT = "Propuesta Comercial"` = último fallback (constante única).
- `Quotation.proposal_effective_print_format` = **solo se persiste al congelar** (Borrador→En Revisión) y
  queda **inmutable**. En Borrador NO se graba: se resuelve dinámicamente.
- **Nueva versión:** `proposal_effective_print_format` NO se copia (`no_copy=1`); la nueva versión hereda el
  formato anterior como `proposal_print_format`, editable mientras siga en Borrador.
- **Segundo Print Format solo para tests:** `Test Proposal Alternate Format` (ficticio, creado en setup de
  test). No usar `Rentabilidad Estimada` (debe demostrarse que es ruta independiente).

## Cambios

1. **Campos**
   - `fixtures/custom_field.json`: `Quotation.proposal_print_format` (Link→Print Format) +
     `Quotation.proposal_effective_print_format` (Link→Print Format, read_only=1, no_copy=1).
   - `doctype/proposal_template/proposal_template.json`: `print_format` (Link→Print Format).
2. **`utils/print_format.py` (nuevo, genérico)**
   - `DEFAULT_COMMERCIAL_PRINT_FORMAT`.
   - `resolve_commercial_print_format(doc)` (congelado → efectivo; Borrador → cadena dinámica).
   - `dynamic_commercial_print_format(doc)` (override → template → default).
   - `validate_print_format(name)` (existe · doc_type=Quotation · no disabled) → error claro (Caso F).
   - `freeze_effective_print_format(doc)` (persiste el efectivo al congelar).
   - `@whitelist get_effective_commercial_print_format(quotation)` (para la ruta A/JS).
3. **`utils/quotation.py`**
   - `on_quotation_validate`: validar `proposal_print_format` si está.
   - `freeze_proposal`: persistir `proposal_effective_print_format`.
   - `attach_proposal_pdfs`: usar el resolver (comercial); `Rentabilidad Estimada` intacto.
4. **`public/js/quotation.js`**
   - Botón comercial: resolver por whitelisted → abrir printview con el formato efectivo.
   - Borrador: mostrar el formato efectivo.
5. **Nueva versión** (`create_new_proposal_version`): heredar formato anterior a `proposal_print_format`;
   no copiar el efectivo.
6. **Validación en Proposal Template**: validar `print_format` si está.

## Pruebas A–G (obligatorias) + setup del Print Format de prueba
A default · B template · C override quotation · D congelamiento inmutable · E nueva versión ·
F formato inválido (bloqueo) · G Rentabilidad no afectada. + validación final 4 familias × ≥2 formatos.

## Estado
- [x] Fase 1 diagnóstico — hecho (BASELINE.md).
- [x] Fase 2 implementación — hecha:
  - Campos: `Quotation.proposal_print_format`, `Quotation.proposal_effective_print_format`,
    `Proposal Template.print_format`.
  - `utils/print_format.py`: resolver + validación + congelamiento + whitelisted (ruta JS).
  - `utils/quotation.py`: valida override en validate; congela efectivo en `freeze_proposal`; attach usa el resolver.
  - `public/js/quotation.js`: botón usa el resolver; muestra el formato efectivo.
  - `proposal_versioning.py`: nueva versión hereda el formato como override (no copia el congelado).
- [x] Tests A–G: **11/11 OK** (`tests/test_print_format_resolution.py`). Print Format de prueba
  `Test Proposal Alternate Format` creado solo en setup de test. Suite completa **167 OK** (1 skip).
- [x] **Validación final manual** — 15/15 en `proposals-acti.dev` (4 familias × 2 formatos: default/template/override,
  freeze inmutable, nueva versión hereda, Rentabilidad independiente). Suite completa 167 OK.
- [x] **Genericización del asset shippeado** — `Propuesta Comercial` sin marca decorativa; logo 100%
  heredado del site (`Company.company_logo`); `public/images/` vacío; PNGs branded preservados fuera del
  repo. `Rentabilidad Estimada` ya era genérico. 0 términos de cliente en assets versionados.
- [x] TASK 6 **COMPLETADO** como infraestructura genérica del app.

## Siguiente: TASK 7 (fuera de este alcance genérico)
**Print Formats específicos del cliente (4, uno por familia) — FUERA del repo público**, en la carpeta
privada del cliente, aplicados solo a su site vía `Proposal Template.print_format`. Diseño a partir de la
revisión visual de los 7 Word (portada, encabezados/pies, logo, tipografías, colores, índice, tablas,
bloques, alcance/entregables, condiciones comerciales, cierre/firmas). Si no hay formato del cliente
configurado → cae al `Propuesta Comercial` genérico del app (resolver de TASK 6).
