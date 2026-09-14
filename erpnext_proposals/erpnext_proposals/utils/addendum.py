"""
Contrato canónico de addendas para erpnext_proposals.

Una **addenda** es una propuesta que modifica el alcance de un Project ya ganado. Su identidad vive
ENTERAMENTE en un `proposal_group` con el patrón reservado ``<ROOT>-ADD-<NN>``:

- La propuesta original conserva su `proposal_group` (el ROOT).
- Cada addenda usa un grupo NUEVO ``ROOT-ADD-NN``; sus revisiones/versiones conservan ese mismo grupo
  (cadena de versionado independiente, vía `create_new_proposal_version`).
- Para el resto de la app `proposal_group` sigue siendo una **clave opaca**: SOLO este módulo conoce la
  semántica de addenda. No se dispersan regex ni parsing por otros módulos, y NO existen campos
  ``addendum_of`` / ``source_proposal_group``: la relación se deriva del propio nombre del grupo.

Primitivas consumibles por `pmo` (server-side, vía ``frappe.get_attr``; NO whitelisted):
- ``create_addendum_quotation(root_quotation) -> str`` — creación ATÓMICA de la siguiente addenda.
- ``resolve_root_project(root_group) -> str`` — Project raíz (para validar antes de aplicar).
- (`apply_addendum_to_project` vive en ``utils.project`` y reutiliza este módulo.)

Concurrencia: la generación de la secuencia ``ADD-NN`` y la creación de la Quotation ocurren en la
**misma transacción** bajo un lock ``SELECT ... FOR UPDATE`` **por ROOT** (mismo mecanismo nativo que
`create_new_proposal_version`). No existe "reservar el string ahora y crear después".
"""

import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import flt

from erpnext_proposals.erpnext_proposals.utils.permissions import assert_can_manage_proposals

# Namespace reservado: ``<ROOT>-ADD-<NN>``. El sufijo ``-ADD-<dígitos>`` al final es la marca canónica.
# `.+` es greedy → para grupos anidados (que no deberían existir) captura el sufijo más externo; la
# resolución de root itera hasta el ROOT real. Solo lo generan `create_addendum_quotation` (nueva
# addenda) y `create_new_proposal_version` (revisión legítima que conserva el mismo grupo).
_ADD_SEP = "-ADD-"
_ADDENDUM_RE = re.compile(r"^(?P<root>.+)-ADD-(?P<seq>\d+)$")


# ── Reconocimiento / parsing (única fuente de la semántica) ──────────────────────


def is_addendum_group(group: str | None) -> bool:
	"""True si `group` casa el patrón reservado ``^<ROOT>-ADD-<NN>$``."""
	return bool(group) and _ADDENDUM_RE.match(group) is not None


def parse_addendum_group(group: str | None) -> tuple[str, int] | None:
	"""Devuelve ``(root, seq)`` si `group` es una addenda; ``None`` en caso contrario."""
	if not group:
		return None
	m = _ADDENDUM_RE.match(group)
	if not m:
		return None
	return m.group("root"), int(m.group("seq"))


def resolve_root_group(group: str | None) -> str | None:
	"""Sube hasta el ROOT real.

	- ``ROOT`` (grupo normal) → ``ROOT``.
	- ``ROOT-ADD-NN`` (addenda o cualquiera de sus versiones) → ``ROOT``.
	Itera de forma defensiva por si existiera un grupo anidado, con guard anti-ciclo.
	"""
	current = group
	seen: set[str] = set()
	while current and current not in seen:
		parsed = parse_addendum_group(current)
		if not parsed:
			return current
		seen.add(current)
		current = parsed[0]
	return current


# ── Guard de namespace reservado (fail-closed) ───────────────────────────────────


def assert_group_not_reserved(doc) -> None:
	"""Impide que una Quotation NUEVA introduzca manualmente un `proposal_group` reservado ``-ADD-NN``.

	Solo se permite cuando lo genera un flujo autorizado, señalado por flags **transitorios** (no
	persistidos, no seteables por REST):
	- ``from_addendum_creation`` → `create_addendum_quotation` (nueva addenda).
	- ``from_proposal_versioning`` → `create_new_proposal_version` (revisión que conserva el grupo).

	Se invoca desde `on_quotation_before_insert` (solo corre en creación), por lo que no interfiere con
	el guardado posterior de addendas ya existentes.
	"""
	if not is_addendum_group(doc.get("proposal_group")):
		return
	if doc.flags.get("from_addendum_creation") or doc.flags.get("from_proposal_versioning"):
		return
	frappe.throw(
		_(
			"El sufijo «-ADD-NN» está reservado para addendas y no puede asignarse manualmente a una "
			"propuesta. Una addenda se crea con su acción dedicada; sus revisiones conservan el grupo "
			"mediante el versionado de propuestas."
		),
		title=_("Grupo de propuesta reservado"),
	)


# ── Secuencia y resolución del Project raíz ──────────────────────────────────────


def _next_addendum_sequence(root: str) -> int:
	"""Siguiente ``NN`` para el ROOT. DEBE llamarse dentro del lock del root (ver `create_addendum_quotation`).

	Sobre-lee con ``LIKE`` (los comodines de SQL en `root` solo amplían el conjunto) y filtra con el
	parser por igualdad exacta de root: el resultado es correcto aunque el root contenga ``_``/``%``.
	"""
	groups = frappe.db.get_all(
		"Quotation",
		filters={"proposal_group": ("like", f"{root}{_ADD_SEP}%")},
		pluck="proposal_group",
		distinct=True,
	)
	max_seq = 0
	for g in groups:
		parsed = parse_addendum_group(g)
		if parsed and parsed[0] == root:
			max_seq = max(max_seq, parsed[1])
	return max_seq + 1


def resolve_root_project(root_group: str) -> str:
	"""Project del ROOT — única fuente de verdad.

	``root_group`` → propuesta **Ganada vigente** del grupo raíz → su ``proposal_project`` → Project
	existente. NUNCA ``Project.project_name``, inferencia por nombre, búsqueda fuzzy, ni un Project
	arbitrario. Lanza si el root no tiene una Ganada vigente o esa Ganada no tiene Project.
	"""
	rows = frappe.get_all(
		"Quotation",
		filters={
			"proposal_group": root_group,
			"docstatus": 1,
			"workflow_state": "Ganada",
			"superseded_by_proposal": ("in", ("", None)),
		},
		fields=["name", "proposal_project"],
	)
	if not rows:
		frappe.throw(
			_(
				"El grupo raíz {0} no tiene una propuesta Ganada vigente; no hay Project raíz que aplicar."
			).format(root_group)
		)
	if len(rows) > 1:
		frappe.throw(
			_("Estado inconsistente: múltiples propuestas Ganada vigentes en el grupo raíz {0}.").format(
				root_group
			)
		)
	project = rows[0].proposal_project
	if not project or not frappe.db.exists("Project", project):
		frappe.throw(
			_(
				"La propuesta raíz Ganada ({0}) no tiene un Project asociado. Genere primero el Project de "
				"la propuesta original antes de aplicar una addenda."
			).format(rows[0].name)
		)
	return project


# ── Creación atómica de la siguiente addenda ─────────────────────────────────────


def create_addendum_quotation(root_quotation: str) -> str:
	"""Crea ATÓMICAMENTE la siguiente addenda ``ROOT-ADD-NN`` a partir de una Quotation de referencia.

	Contrato (consumible por `pmo`):
	1. Recibe una Quotation de referencia del grupo (original, una versión, o incluso una addenda).
	2. Resuelve su ``proposal_group`` **root canónico** (sube hasta el ROOT real).
	3. Adquiere un lock ``SELECT ... FOR UPDATE`` **por el ROOT** (no por el nombre concreto recibido):
	   serializa cualquier intento concurrente del mismo root aunque los callers pasen versiones/addendas
	   distintas del grupo.
	4. Calcula la siguiente secuencia ``ADD-NN`` con el estado bajo lock.
	5. Crea la nueva Quotation-addenda en la MISMA transacción, con ``proposal_group = ROOT-ADD-NN`` y
	   ``proposal_version = 1``.
	6. Devuelve el ``name`` de la nueva Quotation. **No** hace commit manual (atómico con el request del
	   caller: un rollback externo revierte también la addenda).

	Contenido inicial (Alternativa A — la addenda es el DELTA comercial): hereda solo contexto comercial
	seguro (Company, Customer/party, moneda, lista de precios, centro de costo) para que sea editable
	normalmente. NO copia
	items originales, Scope Items originales, `proposal_project`, snapshot ni `proposal_template`: copiar el
	alcance original haría que `apply_addendum_to_project()` volviera a materializar trabajo ya existente.

	Permiso: ``assert_can_manage_proposals`` (autoría comercial, consistente con el versionado). Requiere
	que el root exista (grupo con ≥1 Quotation).
	"""
	assert_can_manage_proposals()

	ref = frappe.get_doc("Quotation", root_quotation)
	root = resolve_root_group(ref.proposal_group)
	if not root:
		frappe.throw(
			_(
				"La Cotización de referencia {0} no tiene Proposal Group; no se puede crear una addenda."
			).format(root_quotation)
		)

	# Lock POR ROOT (mismo mecanismo nativo que create_new_proposal_version). Bloquea las filas del grupo
	# raíz —que siempre existe: contiene la propuesta original— serializando toda creación concurrente de
	# addenda del mismo root. El lock se sostiene hasta el commit de ESTA transacción, que incluye el insert.
	locked = frappe.db.sql(
		"SELECT name FROM `tabQuotation` WHERE proposal_group = %s FOR UPDATE",
		root,
	)
	if not locked:
		frappe.throw(
			_("El grupo raíz {0} no tiene ninguna propuesta; no se puede crear una addenda.").format(root)
		)

	# Secuencia + insert dentro del lock, misma transacción, sin commit manual.
	seq = _next_addendum_sequence(root)
	new_group = f"{root}{_ADD_SEP}{seq:02d}"

	new_doc = frappe.get_doc(
		{
			"doctype": "Quotation",
			"quotation_to": ref.quotation_to,
			"party_name": ref.party_name,
			"company": ref.company,
			"currency": ref.currency,
			"selling_price_list": ref.selling_price_list,
			# Centro de costo: contexto comercial seguro y `reqd=1`, necesario para que la addenda sea
			# editable/guardable normalmente. No es alcance ni items.
			"proposal_cost_center": ref.proposal_cost_center,
			"transaction_date": frappe.utils.today(),
			"proposal_group": new_group,
			"proposal_version": 1,
			# Totales en 0: una Quotation SIN items hace early-return en `calculate_taxes_and_totals`
			# (deja los totales en None) y `set_total_in_words` nativo falla con abs(None). Inicializarlos
			# en 0 —igual que el cliente JS para un borrador vacío— permite guardar la addenda-delta vacía.
			"grand_total": 0,
			"base_grand_total": 0,
			"rounded_total": 0,
			"base_rounded_total": 0,
		}
	)
	# Flag transitorio: autoriza el namespace reservado en on_quotation_before_insert (no persistido,
	# no seteable por REST). skip_scope_generation: sin plantilla no hay alcance que generar, pero se
	# marca explícito para blindar el invariante "la addenda nace como delta vacío".
	new_doc.flags.from_addendum_creation = True
	new_doc.flags.skip_scope_generation = True
	new_doc.insert(ignore_permissions=True, ignore_mandatory=True)
	return new_doc.name


# ── Huella canónica del delta de addenda (ADR-0019 §7.2; porción económica vía ADR-0020) ──────────


def _canon_dependency_codes(raw) -> list:
	"""Canonicaliza `dependency_scope_item_codes` (almacenado como JSON string de una lista de códigos) a
	una lista ordenada de strings. Neutraliza diferencias irrelevantes de serialización (espaciado, orden):
	solo importa el CONJUNTO de códigos declarado. Vacío/invalido → []."""
	if not raw:
		return []
	try:
		parsed = json.loads(raw) if isinstance(raw, str) else raw
	except ValueError, TypeError:
		return []
	if not isinstance(parsed, list):
		return []
	return sorted(str(c) for c in parsed)


def _canon_sort(rows: list) -> list:
	"""Ordena las filas por su representación canónica preservando MULTIPLICIDAD (no deduplica): el orden
	FÍSICO de los child rows deja de influir, pero dos filas idénticas siguen contando como dos."""
	return sorted(rows, key=lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False))


def _addendum_delta_payload(doc) -> dict:
	"""Construye el payload SEMÁNTICO CONGELADO del delta de la addenda (sin identificadores técnicos).

	- Ingreso (Quotation Item): item_code, uom, qty, rate, net_amount + comportamiento económico congelado
	  (proposal_economic_behavior / proposal_billing_interval / _count) — la porción económica del delta se
	  define/consume vía ADR-0020, para que un cambio de recurrencia (NRC/MRC/CAPEX) NO produzca la misma huella.
	- Labor (Quotation Scope Item): code, estimated_hours, activity_type, designation, costing_rate (rate
	  congelado) + planificación (offset/duración/milestone/dependencias canonicalizadas).
	- External (Proposal Required Item): item, qty, uom, frozen_cost_rate, economic_behavior, billing_interval/_count.

	Valores numéricos normalizados con `flt(x, 6)` para estabilidad; strings None → "". Multiplicidad preservada."""
	revenue = [
		{
			"item_code": r.get("item_code") or "",
			"uom": r.get("uom") or "",
			"qty": flt(r.get("qty"), 6),
			"rate": flt(r.get("rate"), 6),
			"net_amount": flt(r.get("net_amount"), 6),
			"economic_behavior": r.get("proposal_economic_behavior") or "",
			"billing_interval": r.get("proposal_billing_interval") or "",
			"billing_interval_count": int(r.get("proposal_billing_interval_count") or 0),
		}
		for r in (doc.get("items") or [])
	]
	labor = [
		{
			"code": s.get("code") or "",
			"estimated_hours": flt(s.get("estimated_hours"), 6),
			"activity_type": s.get("activity_type") or "",
			"designation": s.get("designation") or "",
			"costing_rate": flt(s.get("costing_rate"), 6),
			"planned_start_offset_days": flt(s.get("planned_start_offset_days"), 6),
			"planned_duration_days": flt(s.get("planned_duration_days"), 6),
			"is_milestone": int(bool(s.get("is_milestone"))),
			"dependency_scope_item_codes": _canon_dependency_codes(s.get("dependency_scope_item_codes")),
		}
		for s in (doc.get("quotation_scope_items") or [])
	]
	external = [
		{
			"item": r.get("item") or "",
			"qty": flt(r.get("qty"), 6),
			"uom": r.get("uom") or "",
			"frozen_cost_rate": flt(r.get("frozen_cost_rate"), 6),
			"economic_behavior": r.get("economic_behavior") or "",
			"billing_interval": r.get("billing_interval") or "",
			"billing_interval_count": int(r.get("billing_interval_count") or 0),
		}
		for r in (doc.get("required_items") or [])
	]
	return {
		"revenue": _canon_sort(revenue),
		"labor": _canon_sort(labor),
		"external": _canon_sort(external),
	}


def _canonical_hash(payload: dict) -> str:
	"""SHA-256 de la serialización canónica determinista (claves ordenadas, sin espacios, UTF-8)."""
	canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
	return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_addendum_delta_fingerprint(quotation: str) -> str:
	"""Huella canónica y estable del delta SEMÁNTICO CONGELADO de una addenda formal (ADR-0019 §7.2; la
	porción económica se define/consume vía ADR-0020). **Read-only, server-side, NO whitelisted.**

	Fail-closed: exige addenda canónica `ROOT-ADD-NN`, formal (`docstatus >= 1`) y snapshot económico
	completo (`assert_economic_snapshot_complete`). No hay huella estable para un Borrador. La huella depende
	SOLO del contenido semántico congelado (no de `name`, versión, `proposal_project`, timestamps ni IDs
	técnicos): una nueva versión con el mismo delta produce la MISMA huella. Preserva multiplicidad de filas.

	Consumo futuro por `pmo` (registro de gobernanza + guard de `apply`, fail-closed). Este bloque entrega
	solo la primitive; `pmo` no calcula la huella, la consume. No persiste nada."""
	doc = frappe.get_doc("Quotation", quotation)

	if not is_addendum_group(doc.get("proposal_group")):
		frappe.throw(
			_("get_addendum_delta_fingerprint solo aplica a addendas canónicas «ROOT-ADD-NN» ({0}).").format(
				doc.get("proposal_group") or "—"
			)
		)
	if int(doc.docstatus or 0) < 1:
		frappe.throw(
			_(
				"La huella del delta solo es estable en una addenda formal (docstatus ≥ 1). "
				"Un Borrador no tiene huella comparable."
			)
		)

	# Integridad del snapshot congelado (fail-closed): nunca se calcula huella sobre datos incompletos.
	from erpnext_proposals.erpnext_proposals.utils.quotation import assert_economic_snapshot_complete

	assert_economic_snapshot_complete(doc)

	return _canonical_hash(_addendum_delta_payload(doc))
