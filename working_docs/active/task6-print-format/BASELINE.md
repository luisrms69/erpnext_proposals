# TASK 6 — BASELINE (Fase 1, diagnóstico) — Print Format comercial

**Rama:** `feat/proposal-project-task-integration` (local). Documento genérico (sin datos de cliente).
Baseline levantado antes de modificar código.

---

## Cómo se resuelve HOY el Print Format comercial

Hay **dos rutas independientes**, y **ambas hardcodean** el nombre `Propuesta Comercial`. No comparten
una función de resolución.

### Ruta A — Vista de impresión interactiva (navegador)
- `public/js/quotation.js:111-120` — botón **"Imprimir Propuesta Comercial"**.
- Abre `/printview?doctype=Quotation&name=<name>&format=Propuesta%20Comercial&no_letterhead=0`.
- Usa el `printview` nativo de Frappe (render en vivo del Print Format). **Formato hardcodeado en el URL.**

### Ruta B — Snapshot PDF al congelar (servidor)
- Disparador: `utils/workflow_validations.py:_on_workflow_transition` — en la transición
  **Borrador → En Revisión** llama `freeze_proposal(doc)` (snapshot de secciones + tarifas) y luego
  `attach_proposal_pdfs(doc)`.
- `utils/quotation.py:attach_proposal_pdfs` → `_attach_pdf(print_format="Propuesta Comercial", is_private=0)`
  y `_attach_pdf(print_format="Rentabilidad Estimada", is_private=1)`.
- `_attach_pdf` = `frappe.get_print(doc, print_format=...)` → `get_pdf` → adjunta como `File`. **Hardcodeado.**

**Conclusión (4):** la vista de impresión (A) y la generación de PDF congelado (B) **NO usan la misma
ruta de código**; son dos mecanismos distintos que hoy coinciden solo porque ambos escriben el mismo
nombre a mano.

---

## Print Format interno `Rentabilidad Estimada` (no debe afectarse)
- Botón propio `quotation.js:122-131` (`format=Rentabilidad Estimada`).
- Adjunto propio en `attach_proposal_pdfs` (`is_private=1`).
- Es **independiente** del formato comercial. TASK 6 no debe tocarlo.

---

## Estado actual de campos y metadata
- Quotation: **NO** existe `proposal_print_format` (custom field a crear).
- Proposal Template: campos = `template_name`, `description`, `sections`. **NO** hay `print_format` (a crear).
- Print Formats de la app: `Propuesta Comercial` y `Rentabilidad Estimada` → `doc_type=Quotation`,
  `disabled=0`, `standard=Yes`, `print_format_type=Jinja`.
- `hooks.py:80` (`["name","=","Propuesta Comercial"]`) es el **Workflow** homónimo, NO el Print Format.

## Referencias hardcodeadas a `Propuesta Comercial` (a considerar)
- Producción: `quotation.js` (URL botón), `utils/quotation.py:408-409` (attach).
- Tests: `test_phase_link`, `test_print_format_integrity`, `test_frozen_quotation_integrity`,
  `test_proposal_immutability`, `test_project_task_integration` (usan `frappe.get_print(... "Propuesta Comercial")`).
- `one_offs/*` (no versionados).

---

## Puntos de cambio identificados para la Fase 2
1. **Campo Quotation** `proposal_print_format` (Link→Print Format, opcional) — override por propuesta.
2. **Campo Proposal Template** `print_format` (Link→Print Format, opcional) — default por familia.
3. **Campo Quotation** `proposal_effective_print_format` (read_only, no_copy) — formato **congelado**.
4. **Resolución** `resolve_commercial_print_format(doc)`:
   `Quotation.proposal_print_format` → `Proposal Template.print_format` → default `Propuesta Comercial`
   (nombre default a parametrizar, no hardcode disperso). Con validación (ver §Validaciones del spec).
5. **Ruta A (JS):** el botón debe usar el formato efectivo (leer el resuelto/congelado, no el literal).
6. **Ruta B (attach):** usar el formato resuelto; al congelar, **persistir** `proposal_effective_print_format`
   y usarlo para el adjunto. `Rentabilidad Estimada` intacto.
7. **Inmutabilidad:** propuesta congelada → usa el formato congelado; cambios en Template/default no la afectan.
8. **Nueva versión:** hereda el formato anterior; editable en Borrador.

---

## Pendiente de decisión antes de implementar
- ¿TASK 6 continúa en esta rama (que aún requiere limpieza de historial pre-push) o en rama nueva desde
  `version-16`? (No bloquea el diagnóstico.)
- Confirmar el "default de la app" como constante única (`DEFAULT_COMMERCIAL_PRINT_FORMAT = "Propuesta Comercial"`).
