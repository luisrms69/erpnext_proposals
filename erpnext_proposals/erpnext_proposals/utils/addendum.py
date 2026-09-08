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

import re

import frappe
from frappe import _

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
