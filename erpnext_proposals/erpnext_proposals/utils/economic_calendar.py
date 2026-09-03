# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Motor de la Evaluación Económica por periodos relativos (ADR-0018, Fase 2A).

Construye un calendario **relativo** `Mes 0…N` a partir de capturas que ya existen en la Quotation —Items
vendidos (ingreso), Required Items (costo), costo externo de Fase 1, Scope Items (costo laboral)— más el
**comportamiento económico** configurado por Company (`Proposal Settings`) y el **plazo contractual**. NO se
captura nada financiero por línea. Es de **solo cálculo**: no persiste ningún calendario.

Diseño extensible: el importe por periodo se resuelve vía ``_line_amount_for_period`` (hoy constante) para
no cerrar la puerta a escalamiento / FX / tasas por periodo (Fase 2C) sin agregarlos ahora.

Freeze: en Borrador se resuelve el comportamiento/cadencia en vivo desde el Proposal Settings vigente; en
documentos **submitted** (En Revisión en adelante) se usa **exclusivamente** el snapshot congelado por línea,
de modo que cambios posteriores de configuración no alteran la propuesta histórica.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from erpnext_proposals.erpnext_proposals.utils.cost_matrix import get_designation_cost
from erpnext_proposals.erpnext_proposals.utils.item_cost import resolve_external_cost
from erpnext_proposals.erpnext_proposals.utils.quotation import ONE_TIME, _economic_behavior_for_item

DAYS_PER_MONTH = 30
# Tolerancia de reconciliación (moneda). Absorbe residuos de float en el reparto proporcional del esfuerzo;
# muy por debajo de un centavo de relevancia. Las invariantes fallan si el descuadre supera esto.
_RECON_TOL = 0.05


class EconomicEvaluationError(frappe.ValidationError):
	"""La evaluación económica no reconcilia — nunca se presentan números inconsistentes en silencio."""


# Meses por unidad de intervalo. Sub-mensual (Week/Day) se redondea a mensual (mínimo 1) porque el
# calendario es mensual; documentado en ADR-0018.
_MONTHS_PER_INTERVAL = {"Month": 1.0, "Year": 12.0, "Week": 7.0 / DAYS_PER_MONTH, "Day": 1.0 / DAYS_PER_MONTH}
_SUPPORTED_INTERVALS = ("Month", "Year", "Week", "Day")


def _assert_recurring_valid(interval, count, term, label, company) -> None:
	"""Una cadencia recurrente **inválida** o **sin plazo** es un ERROR de configuración (ADR-0018 hardening):
	nunca fallback silencioso a mensual ni plazo inferido. Identifica el componente afectado. Se llama solo
	para líneas con comportamiento efectivo ``recurring`` (MRC)."""
	comp = _(" (compañía {0})").format(company) if company else ""
	if interval not in _SUPPORTED_INTERVALS:
		frappe.throw(
			_("Componente recurrente '{0}'{1}: intervalo '{2}' inválido. Debe ser uno de: {3}.").format(
				label, comp, interval or _("vacío"), ", ".join(_SUPPORTED_INTERVALS)
			),
			EconomicEvaluationError,
			title=_("Cadencia inválida"),
		)
	if not count or cint(count) <= 0:
		frappe.throw(
			_(
				"Componente recurrente '{0}'{1}: 'cada N intervalos' debe ser mayor que 0 (recibido: {2})."
			).format(label, comp, count),
			EconomicEvaluationError,
			title=_("Cadencia inválida"),
		)
	if cint(term) <= 0:
		frappe.throw(
			_(
				"Componente recurrente (MRC) '{0}'{1} requiere un plazo contractual válido (> 0 meses). "
				"Captura 'Plazo contractual (meses)' en la Quotation."
			).format(label, comp),
			EconomicEvaluationError,
			title=_("Falta plazo contractual"),
		)


def _step_months(interval: str | None, count: int | None) -> int:
	"""Paso en meses de una cadencia **ya validada** (``_assert_recurring_valid``). Month/1→1 (mensual);
	Year/1→12; Month/3→3. Los `max`/fallbacks son defensa en profundidad; la cadencia inválida ya se rechazó
	antes en la evaluación."""
	factor = _MONTHS_PER_INTERVAL.get(interval or "Month", 1.0)
	return max(1, round((count or 1) * factor))


def _occurrence_periods(behavior: str, step: int, term: int) -> list:
	"""Periodos (relativos) en los que ocurre el cargo. one_time/infrastructure → solo Mes 0. recurring →
	Mes 0, step, 2·step, … dentro del plazo. Sin plazo (term≤0) un recurrente degenera a un único Mes 0."""
	if behavior == "recurring":
		horizon = term if term and term > 0 else 1
		return list(range(0, horizon, max(1, step)))
	return [0]


def _parse_offset_days(value) -> int:
	"""`planned_start_offset_days` es Data/string (ADR-0017): parseo defensivo a entero ≥ 0."""
	try:
		# str(value) siempre produce una cadena → float() solo puede lanzar ValueError (nunca TypeError);
		# un único tipo evita la sintaxis de tupla (portabilidad entre versiones de Python/CI).
		return max(0, int(float(str(value).strip())))
	except ValueError:
		return 0


def _line_amount_for_period(amount: float, period: int, occurrences: set) -> float:
	"""Semilla de extensibilidad: importe de una línea en un periodo. Hoy constante (mismo importe en cada
	ocurrencia); Fase 2C podrá inyectar escalamiento/FX como función de ``period`` sin rediseñar el motor."""
	return flt(amount) if period in occurrences else 0.0


def _distribute_over_months(offset_days: int, duration_days: int, is_milestone, cost: float) -> dict:
	"""**Regla ÚNICA** de distribución temporal del costo de esfuerzo (ADR-0018). Devuelve ``{mes: importe}``:

	- ``cost == 0`` → vacío;
	- milestone o ``duration ≤ 0`` → costo puntual en ``floor(offset/30)``;
	- si no, reparto **proporcional** por solapamiento de días en ventanas de 30 días. Conserva el total.

	Nunca descarta costo: si la ejecución rebasa el plazo contractual, los meses resultantes siguen presentes
	(el horizonte del calendario se expande para incluirlos; la evaluación además emite una advertencia)."""
	if not cost:
		return {}
	if is_milestone or duration_days <= 0:
		return {offset_days // DAYS_PER_MONTH: cost}
	first = offset_days // DAYS_PER_MONTH
	last = (offset_days + duration_days - 1) // DAYS_PER_MONTH
	out: dict = {}
	for m in range(first, last + 1):
		mstart, mend = m * DAYS_PER_MONTH, (m + 1) * DAYS_PER_MONTH
		overlap = max(0, min(offset_days + duration_days, mend) - max(offset_days, mstart))
		if overlap:
			out[m] = cost * (overlap / duration_days)
	return out


def _labor_rate_source(row, is_frozen: bool) -> tuple:
	"""Tarifa laboral por hora + **fuente**: snapshot congelado en submitted; en vivo (Cost Matrix) en Borrador."""
	if is_frozen and row.get("rate_locked") and flt(row.get("costing_rate")):
		return flt(row.get("costing_rate")), (row.get("rate_source") or "frozen")
	rate, source = get_designation_cost(row.get("designation"), row.get("activity_type"))
	return flt(rate), source


def _external_rate_source(item_code, uom, txn, is_frozen: bool, locked, frozen_rate, frozen_source) -> tuple:
	"""Costo externo por unidad + **fuente** (buying_item_price / last_purchase_rate / valuation_rate /
	no_purchase / sin_costo): snapshot congelado en submitted; pricing nativo en vivo en Borrador."""
	if is_frozen and locked:
		return flt(frozen_rate), (frozen_source or "frozen")
	rate, source = resolve_external_cost(item_code, uom, txn)
	return flt(rate), source


def _labor_by_month(doc, is_frozen: bool) -> dict:
	"""Costo laboral por mes relativo (agregado). Proyección de ``_scope_effort`` — **misma fuente única** de
	reparto (``_distribute_over_months``); no reimplementa la distribución."""
	return _scope_effort(doc, is_frozen)[2]


def _effective_behavior(row, item_code, is_frozen: bool, company, frozen_fields) -> tuple:
	"""Comportamiento efectivo de una línea: snapshot congelado en submitted; resolución viva en Borrador."""
	b_field, i_field, c_field = frozen_fields
	if is_frozen and row.get(b_field):
		return (row.get(b_field), row.get(i_field) or None, cint(row.get(c_field)) or None)
	return _economic_behavior_for_item(item_code, company)


# Presentación: terminología del cliente (el motor sigue usando one_time/recurring/infrastructure).
GROUP_LABELS = {"one_time": "NRC", "recurring": "MRC", "infrastructure": "CAPEX"}
_ITEMS_FROZEN_FIELDS = (
	"proposal_economic_behavior",
	"proposal_billing_interval",
	"proposal_billing_interval_count",
)
_REQUIRED_FROZEN_FIELDS = ("economic_behavior", "billing_interval", "billing_interval_count")


def group_label(behavior: str) -> str:
	"""Mapea el comportamiento interno a la agrupación visible del cliente (NRC/MRC/CAPEX)."""
	return GROUP_LABELS.get(behavior, "NRC")


def _cadence_label(interval: str | None, count: int | None) -> str:
	c = count or 1
	unit = {
		"Month": ("Mensual", "meses"),
		"Year": ("Anual", "años"),
		"Week": ("Semanal", "semanas"),
		"Day": ("Diario", "días"),
	}
	name, plural = unit.get(interval or "Month", ("Mensual", "meses"))
	return name if c == 1 else f"Cada {c} {plural}"


def _scope_effort(doc, is_frozen: bool):
	"""Detalle de esfuerzo por Quotation Scope Item + labor total atribuible por item_code.

	Devuelve ``(effort_rows, labor_by_item, labor_by_month)``. Reusa la misma regla de distribución que el
	calendario (``_labor_by_month``) para consistencia."""
	effort_rows = []
	labor_by_item: dict = {}
	labor_by_month: dict = {}
	for row in doc.get("quotation_scope_items") or []:
		if not (row.get("include_in_proposal") or row.get("is_internal_cost_task")):
			continue
		rate, rate_source = _labor_rate_source(row, is_frozen)
		hours = flt(row.get("estimated_hours"))
		cost = hours * rate
		offset = _parse_offset_days(row.get("planned_start_offset_days"))
		dur = cint(row.get("planned_duration_days"))
		milestone = 1 if row.get("is_milestone") else 0
		alloc = _distribute_over_months(offset, dur, milestone, cost)  # fuente ÚNICA de reparto
		for m, c in alloc.items():
			labor_by_month[m] = labor_by_month.get(m, 0.0) + c
		item_code = row.get("item_code")
		labor_by_item[item_code] = labor_by_item.get(item_code, 0.0) + cost
		effort_rows.append(
			{
				# Datos HUMANOS (auditoría de mano de obra): actividad + perfil que ejecuta.
				"activity": row.get("title") or row.get("code"),
				"designation": row.get("designation"),  # perfil (dato real de get_designation_cost)
				"hours": hours,
				"rate": rate,
				"rate_source": rate_source,
				"cost": cost,
				"offset_days": offset,
				"duration_days": dur,
				"is_milestone": milestone,
				"periods": sorted(alloc.keys()),
				"alloc": {
					int(m): c for m, c in alloc.items()
				},  # importe por periodo (fuente para trazabilidad)
				# Detalle técnico secundario (trazabilidad de sistema).
				"scope_item": row.get("scope_item"),
				"item_code": item_code,
				"phase": row.get("phase"),
			}
		)
	return effort_rows, labor_by_item, labor_by_month


def get_economic_calendar(quotation_name: str) -> dict:
	"""Calendario económico por periodos — **proyección** del modelo único ``get_economic_evaluation``.

	Fuente ÚNICA de cálculo: no recalcula por su cuenta (evita drift entre Script Report, Quotation JS y
	Print Format). Devuelve ``{currency, term_months, horizon, is_frozen, periods:[{period,revenue,external,
	labor,total_cost,margin}], totals}`` — el calendario financiero puro, sin desglose de componentes.
	"""
	ev = get_economic_evaluation(quotation_name)
	periods = [
		{
			"period": p["period"],
			"revenue": p["revenue"],
			"external": p["external"],
			"labor": p["labor"],
			"total_cost": p["total_cost"],
			"margin": p["margin"],
		}
		for p in ev["periods"]
	]
	return {
		"currency": ev["currency"],
		"term_months": ev["term_months"],
		"horizon": ev["horizon"],
		"is_frozen": ev["is_frozen"],
		"periods": periods,
		"totals": ev["totals"],
	}


@frappe.whitelist()
def get_economic_evaluation(quotation_name: str) -> dict:
	"""Modelo RICO de la Evaluación Económica para presentación (ADR-0018 Fase 2A): resumen, composición por
	agrupación del cliente **NRC/MRC/CAPEX**, tabla de esfuerzo (Scope Items), calendario `Mes 0…N` con
	**trazabilidad** por componente. Misma matemática que ``get_economic_calendar`` (comparten helpers);
	añade agrupación y desglose para la vista integrada en la Quotation y el Print Format. Solo lectura.

	La agrupación es **presentación**: la naturaleza se infiere del comportamiento efectivo por línea
	(`one_time`→NRC, `recurring`→MRC, `infrastructure`→CAPEX). El importe sale de la propuesta; sin re-captura.
	"""
	doc = frappe.get_doc("Quotation", quotation_name)
	doc.check_permission("read")

	is_frozen = doc.docstatus == 1
	company = doc.get("company")
	currency = (
		doc.get("currency")
		or (frappe.db.get_value("Company", company, "default_currency") if company else None)
		or "MXN"
	)
	term = cint(doc.get("proposal_contract_term_months"))
	txn = doc.get("transaction_date")

	effort_rows, labor_by_item, labor_by_month = _scope_effort(doc, is_frozen)
	max_labor_month = max(labor_by_month) if labor_by_month else 0
	horizon = max(term, max_labor_month + 1, 1)

	periods = [
		{
			"period": m,
			"revenue": 0.0,
			"external": 0.0,
			"labor": 0.0,
			"revenue_components": [],
			"external_components": [],
			"labor_components": [],
		}
		for m in range(horizon)
	]
	groups = {
		g: {"lines": [], "revenue": 0.0, "external": 0.0, "labor": 0.0, "margin": 0.0}
		for g in ("NRC", "MRC", "CAPEX")
	}

	def _add_line(
		item_code, label, qty, origin, behavior, interval, count, revenue_amt, ext_rate, ext_source
	):
		grp = group_label(behavior)
		step = _step_months(interval, count)
		occ = [p for p in _occurrence_periods(behavior, step, term) if p < horizon]
		ext_amt = flt(ext_rate) * flt(qty or 0)
		for p in occ:
			# Importe por periodo vía la semilla de extensibilidad (hoy constante; Fase 2C podrá inyectar
			# escalamiento/FX como función de `p` sin rediseñar el motor).
			rev_p = _line_amount_for_period(revenue_amt, p, occ)
			ext_p = _line_amount_for_period(ext_amt, p, occ)
			if rev_p:
				periods[p]["revenue"] += rev_p
				periods[p]["revenue_components"].append(
					{"item_code": item_code, "label": label, "group": grp, "amount": rev_p}
				)
			if ext_p:
				periods[p]["external"] += ext_p
				periods[p]["external_components"].append(
					{
						"item_code": item_code,
						"label": label,
						"group": grp,
						"source": ext_source,
						"amount": ext_p,
					}
				)
		n = len(occ)
		line_labor = flt(labor_by_item.get(item_code, 0.0))
		contractual_rev = flt(revenue_amt) * n
		contractual_ext = ext_amt * n
		line = {
			"item_code": item_code,
			"label": label,
			"origin": origin,  # "sold" (Quotation Item) | "required" (Proposal Required Item)
			"qty": flt(qty),
			"behavior": behavior,
			"group": grp,
			"cadence": _cadence_label(interval, count) if behavior == "recurring" else "—",
			"occurrences": n,
			"revenue_per_period": flt(revenue_amt),
			"external_per_period": ext_amt,
			"external_unit_cost": flt(ext_rate),
			"external_source": ext_source,
			"revenue": contractual_rev,
			"external": contractual_ext,
			"labor": line_labor,
			"margin": contractual_rev - contractual_ext - line_labor,
		}
		groups[grp]["lines"].append(line)
		groups[grp]["revenue"] += contractual_rev
		groups[grp]["external"] += contractual_ext
		groups[grp]["labor"] += line_labor
		groups[grp]["margin"] += line["margin"]

	for row in doc.get("items") or []:
		behavior, interval, count = _effective_behavior(
			row, row.item_code, is_frozen, company, _ITEMS_FROZEN_FIELDS
		)
		label = row.get("item_name") or row.item_code
		if behavior == "recurring":
			_assert_recurring_valid(interval, count, term, label, company)
		revenue = flt(
			row.get("net_amount") or row.get("amount") or (flt(row.get("rate")) * flt(row.get("qty")))
		)
		ext_rate, ext_source = _external_rate_source(
			row.item_code,
			row.get("uom"),
			txn,
			is_frozen,
			row.get("proposal_cost_locked"),
			row.get("proposal_frozen_cost_rate"),
			row.get("proposal_frozen_cost_source"),
		)
		_add_line(
			row.item_code,
			label,
			row.get("qty"),
			"sold",
			behavior,
			interval,
			count,
			revenue,
			ext_rate,
			ext_source,
		)

	for row in doc.get("required_items") or []:
		behavior, interval, count = _effective_behavior(
			row, row.item, is_frozen, company, _REQUIRED_FROZEN_FIELDS
		)
		label = (row.get("item") or "") + " (requerido)"
		if behavior == "recurring":
			_assert_recurring_valid(interval, count, term, label, company)
		ext_rate, ext_source = _external_rate_source(
			row.item,
			row.get("uom"),
			txn,
			is_frozen,
			row.get("cost_locked"),
			row.get("frozen_cost_rate"),
			row.get("frozen_cost_source"),
		)
		_add_line(
			row.item,
			label,
			row.get("qty") or 1,
			"required",
			behavior,
			interval,
			count,
			0.0,
			ext_rate,
			ext_source,
		)

	# Costo laboral por periodo + trazabilidad: usa el reparto YA calculado por _scope_effort (fuente única).
	for er in effort_rows:
		for m, amt in er["alloc"].items():
			if m < horizon:
				periods[m]["labor"] += amt
				periods[m]["labor_components"].append(
					{
						"activity": er["activity"],
						"designation": er["designation"],
						"scope_item": er["scope_item"],
						"item_code": er["item_code"],
						"amount": amt,
					}
				)

	for p in periods:
		p["total_cost"] = p["external"] + p["labor"]
		p["margin"] = p["revenue"] - p["total_cost"]

	totals = {
		"revenue": sum(p["revenue"] for p in periods),
		"external": sum(p["external"] for p in periods),
		"labor": sum(p["labor"] for p in periods),
	}
	totals["total_cost"] = totals["external"] + totals["labor"]
	totals["margin"] = totals["revenue"] - totals["total_cost"]
	totals["margin_pct"] = (totals["margin"] / totals["revenue"] * 100.0) if totals["revenue"] else 0.0

	for g in groups.values():
		g["count"] = len(g["lines"])

	# Horizonte económico: plazo contractual != necesariamente horizonte. El plazo controla la RECURRENCIA
	# (MRC); el horizonte se EXTIENDE por la ejecución (esfuerzo posterior al plazo), sin extender ingresos
	# recurrentes. `economic_horizon_months` es DERIVADO (= nº de periodos), no un campo persistido.
	economic_horizon_months = horizon

	# Advertencias explícitas (no descartar costo en silencio, ADR-0018 §hardening).
	warnings = []
	max_labor_month = max(labor_by_month) if labor_by_month else 0
	if term > 0 and max_labor_month >= term:
		warnings.append(
			{
				"code": "labor_beyond_term",
				"message": _(
					"Existen costos de esfuerzo posteriores al plazo contractual: plazo {0} meses, "
					"horizonte económico {1} meses (esfuerzo hasta el Mes {2}). El costo NO se descarta y "
					"los ingresos recurrentes (MRC) NO se extienden más allá del plazo."
				).format(term, economic_horizon_months, max_labor_month),
			}
		)
	unattributed = totals["labor"] - sum(g["labor"] for g in groups.values())
	if abs(unattributed) > _RECON_TOL:
		warnings.append(
			{
				"code": "unattributed_labor",
				"message": _(
					"Hay costo de esfuerzo no atribuible a una línea vendida/requerida ({0}); "
					"revisar Scope Items con item_code sin línea."
				).format(f"{unattributed:.2f}"),
			}
		)

	model = {
		"quotation": doc.name,
		"proposal_title": doc.get("proposal_title") or doc.get("title"),
		"customer": doc.get("customer_name") or doc.get("party_name"),
		"company": company,
		"currency": currency,
		"term_months": term,
		# Horizonte real necesario para mostrar TODOS los flujos económicos (derivado). `horizon` se conserva
		# como alias por compatibilidad de consumidores (Script Report / JS / Print Format).
		"economic_horizon_months": economic_horizon_months,
		"horizon": horizon,
		"is_frozen": is_frozen,
		"totals": totals,
		"groups": groups,
		"effort": effort_rows,
		"periods": periods,
		"calendar_segments": _collapse_periods(periods),
		"warnings": warnings,
	}
	_assert_reconciled(model)
	return model


def _assert_reconciled(model: dict) -> None:
	"""INVARIANTES: si la evaluación no cuadra, **falla explícito** (nunca números inconsistentes en silencio).

	Verifica: ingreso/costo externo por grupo = total; costo total = externo+esfuerzo; margen = ingreso-costo;
	el calendario suma a los totales (ingreso/externo/esfuerzo/costo/margen); y por periodo, la suma de
	componentes (ingreso/externo/esfuerzo) = total del periodo."""
	t, groups, periods = model["totals"], model["groups"], model["periods"]

	def eq(a, b, label):
		if abs(flt(a) - flt(b)) > _RECON_TOL:
			raise EconomicEvaluationError(f"Evaluación económica no reconcilia — {label}: {a:.4f} ≠ {b:.4f}")

	eq(sum(g["revenue"] for g in groups.values()), t["revenue"], "ingreso por grupo vs total")
	eq(sum(g["external"] for g in groups.values()), t["external"], "costo externo por grupo vs total")
	eq(t["external"] + t["labor"], t["total_cost"], "costo total = externo + esfuerzo")
	eq(t["revenue"] - t["total_cost"], t["margin"], "margen = ingreso - costo total")
	eq(sum(p["revenue"] for p in periods), t["revenue"], "calendario: ingreso")
	eq(sum(p["external"] for p in periods), t["external"], "calendario: costo externo")
	eq(sum(p["labor"] for p in periods), t["labor"], "calendario: costo esfuerzo")
	eq(sum(p["total_cost"] for p in periods), t["total_cost"], "calendario: costo total")
	eq(sum(p["margin"] for p in periods), t["margin"], "calendario: margen")
	for p in periods:
		mp = p["period"]
		eq(sum(c["amount"] for c in p["revenue_components"]), p["revenue"], f"trazabilidad ingreso Mes {mp}")
		eq(
			sum(c["amount"] for c in p["external_components"]),
			p["external"],
			f"trazabilidad externo Mes {mp}",
		)
		eq(sum(c["amount"] for c in p["labor_components"]), p["labor"], f"trazabilidad esfuerzo Mes {mp}")


def _collapse_periods(periods: list) -> list:
	"""Colapsa periodos **consecutivos idénticos** (mismos ingreso/externo/esfuerzo) en segmentos para una
	trazabilidad **inteligente** (p. ej. «Meses 2-11» en vez de 10 filas iguales). Cada segmento conserva los
	componentes del primer periodo del rango (representativos, por ser idénticos)."""
	segments = []
	for p in periods:
		key = (round(p["revenue"], 4), round(p["external"], 4), round(p["labor"], 4))
		if segments and segments[-1]["_key"] == key:
			segments[-1]["to"] = p["period"]
			segments[-1]["months"] += 1
			continue
		segments.append(
			{
				"_key": key,
				"from": p["period"],
				"to": p["period"],
				"months": 1,
				"revenue": p["revenue"],
				"external": p["external"],
				"labor": p["labor"],
				"total_cost": p["total_cost"],
				"margin": p["margin"],
				"revenue_components": p["revenue_components"],
				"external_components": p["external_components"],
				"labor_components": p["labor_components"],
			}
		)
	for s in segments:
		s.pop("_key", None)
		s["label"] = f"Mes {s['from']}" if s["from"] == s["to"] else f"Meses {s['from']}-{s['to']}"
	return segments
