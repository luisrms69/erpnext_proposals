# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-03
**Rama activa:** `feat/required-items` (base `upstream/version-16` = v0.16.0; versión objetivo del PR **0.17.0**)
**Tarea actual:** **Tema 1 — identidad de Scope Items por fila origen** commiteado sobre el checkpoint de la
campaña de Evaluación Económica (`870ffcb`). Todo verde (**558** tests). **Sin push, sin PR.**

## Tema 1 — identidad de Scope Items por fila origen (hecho)

La identidad de `Quotation Scope Item` pasa de `(item_code, scope_item)` a **`(source_row, scope_item)`**:
se materializa **por FILA ORIGEN** (cada `Quotation Item`/`Proposal Required Item`), no por `item_code`. Dos
filas del mismo Item → materializaciones independientes; `qty` no multiplica; Item compartido → una por Item.
Campos nuevos read-only en `Quotation Scope Item`: `source_type` (`sold`/`required`) + `source_row` (name de
la child row origen; Frappe lo asigna antes de `validate`). Generación/add-missing/resync respetan la identidad
por fila origen; snapshots **legacy** sin `source_row` conservan la semántica por `item_code` (sin backfill).
`create_project_from_quotation` resuelve dependencias **por ocurrencia** (elimina el *last-wins* por
`scope_code`): `S1@A1→S2@A1`, `S1@A2→S2@A2`; cross-ocurrencia ambigua → no se inventa regla, se omite y se
reporta (`dependencies_ambiguous`). Task sigue 1 por Quotation Scope Item. Prerequisito para repetir un Item:
`Selling Settings · Allow Item to Be Added Multiple Times`. Tests: `test_scope_item_row_identity.py` (10).

## Campaña previa (Evaluación Económica, commit `870ffcb`)

---

## Recuperación rápida

Sobre Fase 1 (Items requeridos + costo aditivo) y 1 bis (autoload + procurement por Company), esta campaña
añade la **Evaluación Económica** completa. Fuente única: **`utils/economic_calendar.get_economic_evaluation`**
(`get_economic_calendar` la proyecta). El reporte de lectura/aprobación es el Print Format `Rentabilidad
Estimada` (mismo botón «Vista previa/Descargar rentabilidad» + adjunto oficial). **La pestaña «Evaluación
Económica» de la Quotation fue retirada** (no se mantienen dos superficies); en el cliente solo queda la UX de
financiamiento. Ver **ADR-0018**.

## Qué se implementó en la campaña

**Fase 2A + hardening:** naturaleza NRC/MRC/CAPEX por comportamiento económico por Item/Item Group en
`Proposal Settings`; calendario relativo `Mes 0…N`; freeze histórico por línea; invariantes `_assert_reconciled`
→ `EconomicEvaluationError`; determinismo; cadencia recurrente inválida = error; MRC exige plazo; `term_months`
≠ `economic_horizon_months`.

**Fase 2B — financiamiento del CAPEX** (capa aditiva; NO toca `total_cost`/`margin` de 2A):
- Amortización PMT vencida mensual (`_amortize`) + `_effective_financing`; capa `financial_cost` /
  `total_cost_with_financing` / `margin_after_financing`.
- Defaults por Company (`default_financing_term_months`/`default_financing_cost_rate`) = **solo precarga** al
  activar (`_default_financing`); tras eso la **Quotation es autoritativa** — el motor lee tasa/plazo del doc
  **sin fallback** (una **tasa 0 % explícita es válida**). Freeze por **inmutabilidad** (`allow_on_submit=0`).
- Custom fields en Quotation: `proposal_financing_enabled/_financed_amount/_financing_term_months/
  _financing_annual_cost_rate/_financing_fees_amount` (+ section break). Fail-closed (financiado ≤0/>CAPEX,
  plazo ≤0, tasa <0, comisiones <0, financiamiento sin CAPEX → error). Invariantes 2B en `_assert_reconciled`.

**Reporte `Rentabilidad Estimada` (presentación, aprobado):** estructura narrativa, paginación por contenido.
- **APU por componente vendido:** precio → insumos (costo externo, `unit × qty` en CAPEX) → esfuerzo (actividad
  · perfil · horas · tarifa, + **resumen por perfil**) → costo integrado → margen.
- **Required Items = costos requeridos**, no productos con margen negativo: bloque «Costos requeridos no
  asignados» (no hay vínculo de dato Item vendido → Required Item; **sin prorrateo**).
- **Puente** «Resultado integrado»: margen directo de vendidos − no asignados = operativo − financiero = final.
- Anexo: **amortización** + **matriz de trazabilidad temporal** compacta (una fila por patrón; recurrentes en
  rango, financiamiento resumido) + **controles de reconciliación**.
- Campos descriptivos del motor (sin tocar totales): `unit_price`, `impact_label`, `financeable`,
  `integrated_cost`, `margin_pct`, `effort`, `effort_by_profile`, `effort_totals`, bloque `apu`, `temporal`.
- La pestaña de la Quotation se retiró: se eliminaron los custom fields `proposal_economic_tab` /
  `proposal_economic_evaluation_html` (solo-UI) del fixture, del allowlist de `hooks.py` y de los sites dev.

## Decisiones vigentes que no están en el código

- El reporte oficial se genera por **Gotenberg** (Chromium) → PDF limpio; el perfil del PF sigue `legacy`
  (wkhtmltopdf) porque `proposal_gotenberg_url` **no está configurado** en el entorno de desarrollo. Adoptar
  Gotenberg de forma estable requiere esa config (ADR-0015). No se hicieron hacks de URL local; el PF oculta la
  barra de acciones del print-view (`.action-banner`) por CSS.
- No existe relación de dato Item vendido → Required Item; por eso los costos requeridos quedan en el pool «no
  asignados». Resolver esa relación queda fuera de alcance de esta campaña.
- Coexisten dos fuentes económicas: `get_economic_evaluation` (nueva, canónica) y el legacy
  `get_profitability_data` (Script Report `Profitability Estimate`). No tocar ahora; deprecación a decidir.

## No repetir

- **Fuente única de cálculo:** todo (Script Report / PF / PDF) consume `get_economic_evaluation`; no
  reimplementar totales ni la distribución temporal en ningún consumidor.
- NRC/MRC/CAPEX es **presentación** inferida de la config; preventa **no** clasifica por línea ni captura
  cadencias. El importe sale de la propuesta; sin re-captura de precio.
- Cadencia inválida / MRC sin plazo → **error explícito**, nunca fallback silencioso.
- QtWebKit (wkhtmltopdf sin parchar) **no** soporta `var()` CSS ni gradientes → hex literal, sin flexbox; KPIs
  en tablas. Válido en wkhtmltopdf y Gotenberg.

## Próximo paso

Commit de control (sin push/PR). Para publicar: `/ship push` (autorización aparte) → `/ship pr` hacia
`version-16` (con gate de versionado contra `upstream/main`). Fase 2C (cobros/cash flow, VPN/TIR,
FX/escalamiento) queda diferida.

## Plan que estoy siguiendo

Campaña de Evaluación Económica (ADR-0018), rama `feat/required-items`. Estado: **implementada, endurecida y
con presentación aprobada; lista para commit de control**. Suite: **548/548**. `ruff`/`format`/`prettier`/
`mkdocs --strict`: limpios.
