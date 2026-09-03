# CONTINUITY.md — erpnext_proposals

**Fecha:** 2026-09-03
**Rama activa:** `feat/required-items` (base `upstream/version-16` = v0.16.0; versión objetivo del PR **0.17.0**)
**Tarea actual:** checkpoint de **Fase 2A** (Evaluación Económica NRC/MRC/CAPEX) + **hardening**, todo verde.
Próximo: **Fase 2B** (CAPEX/financiamiento: monto financiado, plazo, tasa, PMT, propio vs tercero). **Sin push.**

---

## Recuperación rápida

Sobre Fase 1 (Items requeridos + costo aditivo) y 1 bis (autoload + procurement por Company), Fase 2A añade
la **Evaluación Económica**: naturaleza **NRC/MRC/CAPEX** inferida del **comportamiento económico** por
Item/Item Group (`Proposal Settings`, por Company), calendario relativo `Mes 0…N`, freeze histórico. Motor
único: **`utils/economic_calendar.get_economic_evaluation`** (`get_economic_calendar` lo proyecta). El reporte
ejecutivo **sustituyó** el Print Format `Rentabilidad Estimada` (mismo botón «Vista previa/Descargar
rentabilidad»); pestaña «Evaluación Económica» = memoria de cálculo; Script Report `Evaluacion Economica`.

## Qué se implementó (Fase 2A + hardening)
- **Config:** child `Proposal Economic Behavior Rule` + `economic_behavior_rules`/`default_contract_term_months`
  en `Proposal Settings`. Precedencia Item > Item Group > `one_time`. Mapeo visible one_time→NRC,
  recurring→MRC, infrastructure→CAPEX (solo presentación).
- **Captura:** único campo nuevo `Quotation.proposal_contract_term_months` (precargado, editable).
- **Motor:** distribución temporal única `_distribute_over_months`; freeze por línea de behavior/interval/count
  (Quotation Item + Required Item); costo externo/tarifa con **fuente**; esfuerzo con **actividad + perfil
  (designation) + horas/tarifa/costo**. On-demand, nada derivado persistido.
- **Invariantes** (`_assert_reconciled` en cada evaluación) → `EconomicEvaluationError` si no reconcilia.
  **Determinismo** probado. **Cadencia recurrente inválida = error** (nunca fallback a mensual). **MRC exige
  plazo válido**; NRC/CAPEX pueden ir sin plazo. **`term_months` ≠ `economic_horizon_months`** (el horizonte
  se extiende por esfuerzo posterior al plazo, sin extender ingresos MRC; warning `labor_beyond_term`).
- **Reporte:** PF profesional (HTML/CSS propio, barras CSS, sin `var()`; robusto en wkhtmltopdf y Gotenberg)
  en `print_format/rentabilidad_estimada/`, consume `get_economic_evaluation` vía jinja method.
- Tests: `test_economic_calendar.py` (**69**); suite completa **513 OK**. ruff/prettier/mkdocs verdes.

## Pendientes / notas
- **Fase 2B (CAPEX/financiamiento)** y **2C (Payment Terms/cash flow, VPN/TIR, escalamiento, FX):** no
  implementar sin autorización. El calendario 2A es **económico/devengado ≠ flujo de caja** (VPN/TIR sobre
  cash flow en 2C).
- **Deuda de compatibilidad:** coexisten dos fuentes económicas — `get_economic_evaluation` (nueva) y el
  legacy `get_profitability_data` (Script Report `Profitability Estimate`). No tocar ahora; riesgo de
  divergencia si se comparan ambos reportes. Deprecación a decidir después.
- **Estética del Print Format: pendiente** (no alcanza aún las 3 referencias visuales). Pase posterior.
- **Config Gotenberg (infra, NO repo):** `proposal_gotenberg_url` sin configurar en proposals.dev y PF en
  perfil `legacy` → hoy renderiza por wkhtmltopdf. Para usar Gotenberg: site config + `proposal_renderer_profile
  = gotenberg-v1`. Requiere autorización (cambios de configuración del sitio).
- **Operativo:** `bench migrate` en dev sin worker deja locks huérfanos (erpnext_custom Role Profile) →
  `DocumentLockedError`. Fix: `rm sites/<site>/locks/*.lock` + migrate.
- Demo en `proposals.dev`: `SAL-QTN-2026-00102` (Borrador) y `00103` (congelada). Scripts en `/tmp` (no repo).

## No repetir
- **Fuente única de cálculo:** todo (Script Report / pestaña / PF / PDF) consume `get_economic_evaluation`;
  no reimplementar totales ni la distribución temporal en ningún consumidor.
- NRC/MRC/CAPEX es **presentación** inferida de la config; preventa **no** clasifica por línea ni captura
  cadencias. El importe sale de la propuesta; sin re-captura de precio.
- Cadencia inválida / MRC sin plazo → **error explícito**, nunca fallback silencioso.
- QtWebKit (wkhtmltopdf sin parchar) **no** soporta `var()` CSS ni gradientes → usar hex literal + barras CSS.
- **Nunca** datos de cliente en archivos trackeados del repo.
