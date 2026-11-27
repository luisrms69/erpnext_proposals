"""Cargador idempotente de catálogos de propuestas (genérico, reutilizable).

Carga la capa EDITORIAL/de PRESENTACIÓN de un catálogo desde un archivo JSON externo a la app,
indicado por ruta. El JSON del catálogo NO se versiona en la app: es dato específico de cada
implementación/cliente y vive fuera del repositorio.

Alcance del loader (tras la depuración de fuentes de verdad):
- Proposal Sections (contenido narrativo/editorial);
- contenido editorial de Items (methodology / expected result / scope limit / service text, etc.):
  actualiza campos de un Item que YA existe; el loader NUNCA crea Items;
- Letter Heads dedicados (branding);
- Print Formats y su versionamiento declarativo (presentación);
- vaciado explícito de campos editoriales (`clear_fields`).

Los datos MAESTROS FUNCIONALES (Proposal Templates y su estructura, Scope Items, Proposal Phases,
registro/flags funcionales de Item, Payment Terms/Templates, Designations, Skills, reglas de
comportamiento económico y sus relaciones) ya NO se distribuyen por el pack: se administran
EXCLUSIVAMENTE desde ERPNext/Frappe (Desk). El pack dejó de ser una segunda fuente de verdad para
ellos y el loader no los crea, actualiza, compara ni genera conflictos sobre ellos.

Ejecución explícita por site (nunca automática en migrate/install):

    # dry-run (por defecto, no escribe):
    bench --site <site> execute erpnext_proposals.erpnext_proposals.catalog_data.catalog_loader.run \\
        --kwargs "{'catalog_path': '/ruta/externa/mi_catalogo.json'}"

    # carga real:
    bench --site <site> execute erpnext_proposals.erpnext_proposals.catalog_data.catalog_loader.run \\
        --kwargs "{'catalog_path': '/ruta/externa/mi_catalogo.json', 'dry_run': False}"

Si no se indica catalog_path, se usa `sample_catalog.json` (datos ficticios de ejemplo/tests).

Propiedades garantizadas:
- dry_run=True por defecto (no escribe sin bandera explícita);
- idempotencia real (get-or-create por identidad; re-ejecutable sin duplicar);
- transacción todo-o-nada (rollback ante cualquier error; commit solo al final);
- crea únicamente lo inexistente (salvo Items: nunca los crea, solo actualiza contenido editorial);
- reutiliza las 10 Sections base y NO las modifica;
- update_content: actualiza el contenido de registros PROPIOS del catálogo cuando difieran;
- detecta y REPORTA conflictos (registro existente con contenido distinto), sin resolverlos;
- reporte final: creados / reutilizados / actualizados / sin cambios / conflictos.
"""

import json
import os

import frappe
from frappe import _

# Catálogo de ejemplo con datos ficticios (para demo/tests). El catálogo real se pasa por ruta.
SAMPLE_CATALOG = os.path.join(os.path.dirname(__file__), "sample_catalog.json")


# Print Formats que el loader NUNCA debe crear, modificar ni tocar. Assets del repo público
# (file-based / standard) cuya fuente de verdad es Git, no un catálogo externo.
PROTECTED_PRINT_FORMATS = frozenset(
	{
		"Propuesta Comercial",
		"Rentabilidad Estimada",
	}
)


# Campos de Print Format que el seeder administra desde el catálogo (`_seed_print_formats`). El resto
# usa el default del DocType. `proposal_renderer_profile` (ADR-0015, v10) permite que el catálogo
# declare el motor de render del formato (`legacy`/`gotenberg-v1`) igual que html/css; sigue protegido
# como presentación en formatos históricos (ADR-0011).
_PRINT_FORMAT_MANAGED_FIELDS = (
	"doc_type",
	"print_format_type",
	"standard",
	"custom_format",
	"disabled",
	"module",
	"page_number",
	"font_size",
	"margin_top",
	"margin_bottom",
	"margin_left",
	"margin_right",
	"html",
	"css",
	"proposal_renderer_profile",
)


# Las 10 Sections base (after_install) NUNCA se crean ni modifican por el seeder.
BASE_SECTIONS = frozenset(
	{
		"Resumen Ejecutivo",
		"Objetivo del Proyecto",
		"Modalidad de Trabajo",
		"Metodologia",
		"Criterios de Aceptacion",
		"Responsabilidades del Cliente",
		"Supuestos",
		"Exclusiones",
		"Control de Cambios",
		"Cierre del Proyecto",
	}
)


# Versión de capacidades del loader. Se incrementa cuando cambian las capacidades que un catálogo
# externo puede requerir. El instalador de producción la usa para rechazar un app desactualizado.
# v3: el loader NO crea/actualiza UOM ni Item Groups (masters fiscales) — solo los referencia.
# v4: soporte de Payment Terms / Payment Terms Templates (condiciones de pago corporativas).
# v5: planeación PMO en Scope Item (planned_start_offset_days/planned_duration_days/is_milestone),
#     dependencias de catálogo (depends_on, 2º paso idempotente) y erpnext_item pendiente
#     (Scope Item sin Item comercial existente, vinculado al re-ejecutar).
# v6: Designations (erpnext) y Skills (hrms) idempotentes por nombre + relación nativa
#     Designation.skills (child Designation Skill), con gate HRMS: sin HRMS las Skills/relaciones
#     quedan 'pending' y se completan al re-ejecutar. NO crea Activity Types/Costs/tarifas/empleados.
# v7: Tags nativos de Frappe declarados por línea en el catálogo (clave `tags` de cada Proposal
#     Phase) → se materializan sobre la Proposal Phase con DocTags (add-only, no destructivo: nunca
#     borra Tags ajenos). Fuente que la app propaga a la Task-fase padre al crear el Project.
# v8: Versionamiento declarativo de Print Formats (clave `print_format_versions`): al sustituir un
#     formato por una versión nueva, deshabilita el anterior (disabled=1; ADR-0011 permite `disabled`
#     en históricos, nunca su contenido), adjunta un changelog como File al nuevo formato y repunta
#     los Proposal Templates del pack al nuevo. Genérico e idempotente; no borra nada.
# v9: Letter Heads dedicados (clave `letter_heads`) + `Proposal Template.letter_head`. Siembra
#     Letter Heads de branding SIN marcarlos default (is_default=0 es propiedad del catálogo) y
#     los enlaza por nombre desde el Template; la app copia Template.letter_head → Quotation.letter_head
#     al aplicar la plantilla. Selección explícita por nombre, independiente del default del sitio.
# v10: el catálogo puede declarar `proposal_renderer_profile` (`legacy`/`gotenberg-v1`) en un Print
#      Format; `_seed_print_formats` lo administra igual que html/css (ADR-0015). Completa la capacidad
#      genérica del renderer desacoplado para que un pack pueda adoptar Gotenberg de forma declarativa.
# v11: vaciado explícito de campos (`clear_fields`) por objeto: un catálogo puede declarar qué campos de
#      un registro existente deben quedar vacíos. Opt-in (la ausencia de un campo NO borra nada),
#      genérico para los tipos soportados, idempotente, respeta update_content/dry_run y valida el campo
#      (existe, no obligatorio, no sistema/estructura/tabla). Resuelve el hueco: `update_content` no
#      podía anular un campo que desaparece del JSON (`_seed_clear_fields`).
# v12: DEPURACIÓN de fuentes de verdad — el loader deja de sembrar/sincronizar los MAESTROS FUNCIONALES
#      que ahora se administran solo en Desk: Proposal Templates (y su estructura), Scope Items (y sus
#      relaciones/dependencias), Proposal Phases (y sus Tags), registro/flags funcionales de Item,
#      Payment Terms / Payment Terms Templates, Designations, Skills y `economic_behavior_rules`. Se
#      retiran esos seeders y sus capacidades (`designations_skills`, `phase_tags`, `payment_terms`,
#      `economic_behavior_rules`, `scope_pmo_planning`). El loader conserva SOLO la capa editorial/de
#      presentación: Sections, contenido editorial de Item (sin crear Items), Letter Heads, Print
#      Formats + versionamiento y `clear_fields` sobre tipos editoriales. `clear_fields` deja de
#      admitir templates/scope_items/phases (tipos ya no gestionados por el pack).
# v13: REACTIVACIÓN CONTROLADA de categorías funcionales requeridas por paquetes de soporte (ADR pendiente):
#      `templates` (Proposal Template + su estructura de Sections), `scope_items` (maestros + relación N:M
#      `erpnext_items` + `default_assignee` validado fail-closed contra User del site), `support_items`
#      (SOLO Items organizativos no vendibles/comprables/stock; fail-closed; nunca masters fiscales) y
#      `email_templates` (Email Template nativo). Reutiliza los seeders previos (recuperados de 20434dc^);
#      idempotente, con control de conflictos y validación de referencias. NO reactiva phases, designations,
#      skills, payment_terms ni economic_behavior_rules (siguen administrados en Desk).
LOADER_CAPS_VERSION = 13


def capabilities() -> dict:
	"""Reporta (y devuelve) las capacidades del loader / pipeline de impresión. La usa el instalador
	de producción para DETECTAR Y RECHAZAR una versión del app sin las capacidades requeridas.

	    bench --site <site> execute erpnext_proposals.erpnext_proposals.catalog_data.catalog_loader.capabilities
	"""
	from erpnext_proposals.erpnext_proposals.utils import printing

	caps = {
		"caps_version": LOADER_CAPS_VERSION,
		# Contenido EDITORIAL de Item (nunca crea Items; solo actualiza campos de contenido).
		"items": callable(globals().get("_seed_items")),
		# Vaciado explícito de un campo editorial (null explícito distinto de omitir la clave).
		"explicit_null": callable(globals().get("_managed_fields")),
		"print_formats": callable(globals().get("_seed_print_formats")),
		"protected_print_formats": bool(PROTECTED_PRINT_FORMATS),
		"get_logo_data_uri": callable(getattr(printing, "get_logo_data_uri", None)),
		# v8: Versionamiento declarativo de Print Formats (deshabilitar anterior + changelog).
		"print_format_versions": callable(globals().get("_seed_print_format_versions")),
		# v9: Letter Heads dedicados (branding no-default).
		"letter_heads": callable(globals().get("_seed_letter_heads")),
		# v10: el catálogo puede declarar el renderer profile de un Print Format (ADR-0015).
		"renderer_profile": "proposal_renderer_profile" in _PRINT_FORMAT_MANAGED_FIELDS,
		# v11: vaciado explícito y opt-in de campos editoriales (`clear_fields`) por objeto.
		"clear_fields": callable(globals().get("_seed_clear_fields")),
		# v13: categorías funcionales reactivadas de forma CONTROLADA (requeridas por paquetes de soporte).
		"templates": callable(globals().get("_seed_templates")),
		"scope_items": callable(globals().get("_seed_scope_items")),
		"support_items": callable(globals().get("_seed_support_items")),
		"email_templates": callable(globals().get("_seed_email_templates")),
		# Masters funcionales que SIGUEN administrados solo en Desk (no reactivados): Phases, Payment Terms,
		# Designations, Skills, economic_behavior_rules. Se verifica por AUSENCIA de sus seeders.
		"no_desk_only_master_writes": not any(
			callable(globals().get(fn))
			for fn in (
				"_seed_phases",
				"_seed_payment_terms",
				"_seed_payment_terms_templates",
				"_seed_designations",
				"_seed_skills",
				"_seed_economic_behavior_rules",
			)
		),
		# El loader NO tiene capacidad de sembrar masters fiscales (UOM / Item Groups).
		"no_fiscal_master_writes": not callable(globals().get("_seed_item_groups"))
		and not callable(globals().get("_seed_uoms")),
	}
	caps["all_present"] = all(v for k, v in caps.items() if k != "caps_version")
	print("CAPABILITIES:" + json.dumps(caps, ensure_ascii=False))
	return caps


def run(catalog_path: str | None = None, dry_run: bool = True, update_content: bool = False) -> dict:
	"""Punto de entrada. dry_run=True por defecto: no escribe, solo reporta el plan.

	catalog_path: ruta al JSON del catálogo (externo a la app). Si None, usa sample_catalog.json.
	update_content=True: además de crear lo inexistente, ACTUALIZA el contenido de los registros
	PROPIOS del catálogo cuando difieran. NUNCA toca las 10 Sections base ni secciones foráneas en uso.
	"""
	dry_run = _as_bool(dry_run)
	update_content = _as_bool(update_content) if update_content is not False else False
	data = _load_catalog(catalog_path)
	# Directorio del catálogo: base para resolver assets referenciados por ruta relativa
	# (p. ej. html_file/css_file de un Print Format), que viven junto al JSON del catálogo.
	catalog_dir = os.path.dirname(os.path.abspath(catalog_path or SAMPLE_CATALOG))
	report: dict = {
		"created": [],
		"reused": [],
		"updated": [],
		"unchanged": [],
		"conflicts": [],
		# Scope Items cuyo erpnext_item apunta a un Item que aún no existe: se dejan sin vincular
		# y se completan al re-ejecutar la sincronización cuando el Item exista.
		"pending": [],
	}

	try:
		# Capa editorial: Sections (contenido narrativo). Devuelve el remap para `clear_fields`.
		section_remap = _seed_sections(
			data.get("sections", []), report, dry_run, update_content, set(data.get("versioned", []))
		)
		# v13: Item organizativo (p. ej. COORD-LICENCIAS) ANTES de los Scope Items que lo referencian por la
		# relación N:M `erpnext_items`. Acotado y fail-closed (solo Items no vendibles/comprables/stock).
		_seed_support_items(data.get("support_items", []), report, dry_run, update_content)
		# v13: Scope Items (maestros funcionales reactivados de forma controlada), con validación fail-closed
		# de `default_assignee` (User debe existir y estar habilitado en el site destino).
		_seed_scope_items(data.get("scope_items", []), report, dry_run, update_content)
		# Contenido EDITORIAL de Items. El loader NUNCA crea Items (el registro funcional se administra
		# en Desk): si el Item no existe, se reporta como pendiente y se omite. UOM/Item Groups tampoco
		# se crean (masters fiscales de facturacion_mexico).
		_seed_items(data.get("items", []), report, dry_run, update_content)
		# Letter Heads dedicados (branding). NUNCA se marcan como default.
		_seed_letter_heads(data.get("letter_heads", []), report, dry_run, update_content)
		# Print Formats. Formatos sustituidos: el versionador es dueño de su `disabled`; _seed_print_formats
		# no lo gestiona.
		superseded_pf = {
			v.get("supersedes") for v in data.get("print_format_versions", []) if v.get("supersedes")
		}
		_seed_print_formats(
			data.get("print_formats", []),
			catalog_dir,
			report,
			dry_run,
			update_content,
			superseded=superseded_pf,
		)
		# Versionamiento de Print Formats: DESPUÉS de crear el formato nuevo (print_formats). Deshabilita
		# el anterior y adjunta changelog. (El repunte de Proposal Templates ya no aplica: los templates
		# se administran en Desk; los catálogos no declaran `templates` en print_format_versions.)
		_seed_print_format_versions(
			data.get("print_format_versions", []),
			catalog_dir,
			report,
			dry_run,
			declared={pf.get("name") for pf in data.get("print_formats", [])},
		)
		# v13: Proposal Templates (DESPUÉS de Sections/Print Formats/Letter Heads: referencian esos nombres).
		_seed_templates(data.get("templates", []), section_remap, report, dry_run, update_content)
		# v13: Email Templates nativos del flujo (p. ej. Propuesta Ganada PMO).
		_seed_email_templates(data.get("email_templates", []), report, dry_run, update_content)
		# Vaciado explícito y opt-in de campos editoriales (`clear_fields`) — DESPUÉS de los seeders, de
		# modo que el estado deseado del catálogo prevalezca sobre lo que ellos hayan sembrado.
		_seed_clear_fields(data, section_remap, report, dry_run, update_content)
	except Exception:
		frappe.db.rollback()
		raise

	if dry_run:
		frappe.db.rollback()
	else:
		frappe.db.commit()  # nosemgrep — carga explícita de catálogo por site, autorizada por el usuario

	_print_report(report, dry_run, data)
	return report


# ─────────────────────────────────────────────────────────────────────────────
# Seeders por DocType
# ─────────────────────────────────────────────────────────────────────────────


def _seed_sections(sections: list, report: dict, dry_run: bool, update_content: bool, versioned: set) -> dict:
	"""Crea/actualiza las secciones del catálogo y devuelve el remap {canónico: nombre_real}.

	- Los nombres en 'versioned' colisionan (BD acento/caso-insensible) con una sección base o
	  foránea en uso → el registro propio del catálogo es la versión sufijada '<nombre> 2' (título
	  limpio); nunca se toca la base ni la foránea.
	- El resto usa su nombre canónico.
	- update_content=True → si el registro PROPIO difiere, se ACTUALIZA su contenido.
	  Nunca se actualizan las 10 Sections base ni las secciones foráneas.
	Idempotente.
	"""
	remap: dict = {}
	for s in sections:
		remap[s["section_name"]] = _resolve_section(s, report, dry_run, update_content, versioned)
	return remap


def _owned_name(canonical: str, versioned: set) -> str:
	"""Registro propio del catálogo. Si 'canonical' está en 'versioned' (colisiona con una sección
	base o foránea en uso), se usa la versión sufijada '<nombre> 2'; de lo contrario, el canónico."""
	return f"{canonical} 2" if canonical in versioned else canonical


def _resolve_section(s: dict, report: dict, dry_run: bool, update_content: bool, versioned: set) -> str:
	canonical = s["section_name"]
	expected = {
		"title": s.get("title") or canonical,
		"content": s.get("content", ""),
		"is_executive_summary": s.get("is_executive_summary", 0),
	}
	ours = _owned_name(canonical, versioned)
	suffix = "" if ours == canonical else f"  (versión de '{canonical}', título limpio)"

	if not frappe.db.exists("Proposal Section", ours):
		if not dry_run:
			_create_section(ours, expected)
		report["created"].append(f"Proposal Section '{ours}'{suffix}")
		return ours
	if _section_matches(ours, expected):
		report["unchanged"].append(f"Proposal Section '{ours}'")
		return ours
	# Existe y difiere.
	if update_content and ours not in BASE_SECTIONS:
		if not dry_run:
			_update_section(ours, expected)
		report["updated"].append(f"Proposal Section '{ours}'{suffix}")
		return ours
	report["conflicts"].append(f"Proposal Section '{ours}': difiere del catálogo (usar update_content)")
	return ours


def _create_section(section_name: str, expected: dict) -> None:
	frappe.get_doc(
		{
			"doctype": "Proposal Section",
			"section_name": section_name,
			"title": expected["title"],
			"content": expected["content"],
			"is_executive_summary": expected["is_executive_summary"],
			"enabled": 1,
		}
	).insert(ignore_permissions=True)


def _update_section(section_name: str, expected: dict) -> None:
	doc = frappe.get_doc("Proposal Section", section_name)
	doc.title = expected["title"]
	doc.content = expected["content"]
	doc.is_executive_summary = expected["is_executive_summary"]
	doc.save(ignore_permissions=True)


def _section_matches(name: str, expected: dict) -> bool:
	current = frappe.db.get_value(
		"Proposal Section", name, ["title", "content", "is_executive_summary"], as_dict=True
	)
	return not _diff(expected, current)


def _seed_items(items: list, report: dict, dry_run: bool, update_content: bool = False) -> None:
	"""Actualiza el CONTENIDO EDITORIAL de Items que YA existen. Identidad: item_code.

	El registro/configuración funcional del Item (item_name, item_group, stock_uom, is_stock_item,
	is_sales_item, is_purchase_item) se administra EXCLUSIVAMENTE en Desk: el loader NUNCA crea Items ni
	toca esos campos. Solo administra los campos EDITORIALES (contenido de propuesta) que el catálogo
	provee, y únicamente sobre un Item existente. Si el Item no existe, se reporta como pendiente y se
	omite (nunca se crea desde el pack). Solo se comparan/actualizan los campos provistos (no se fuerzan
	vacíos salvo null explícito)."""
	fields = [
		# Campos EDITORIALES (contenido de propuesta). Se administran igual: clave presente fija el valor,
		# null explícito limpia, clave ausente no toca. NO se administra ningún campo de registro/flags.
		"description",
		"proposal_methodology",
		"proposal_expected_result",
		"proposal_scope_limit",
		# Características canónicas del servicio (fuente única; consumidas por binding en Sections).
		"proposal_service_validity",
		"proposal_min_unit",
		"proposal_service_hours",
	]
	for it in items:
		code = it["item_code"]
		label = f"Item '{code}'"
		provided, cleared = _managed_fields(it, fields)
		keys = list(provided.keys()) + list(cleared)
		if not frappe.db.exists("Item", code):
			# El loader no crea Items: el registro funcional se administra en Desk. Se reporta y se omite;
			# al re-ejecutar cuando el Item exista, su contenido editorial se aplicará.
			report["pending"].append(
				f"{label}: el Item no existe — el loader no crea Items (créalo en Desk); contenido editorial omitido"
			)
			continue

		current = frappe.db.get_value("Item", code, keys, as_dict=True) if keys else {}
		diffs = _diff_managed(provided, cleared, current)
		if not diffs:
			report["unchanged"].append(label)
		elif update_content:
			if not dry_run:
				doc = frappe.get_doc("Item", code)
				for f, v in provided.items():
					doc.set(f, v)
				for f in cleared:
					doc.set(f, None)
				doc.save(ignore_permissions=True)
			report["updated"].append(f"{label}: {diffs}")
		else:
			report["conflicts"].append(f"{label}: {diffs}")


_LETTER_HEAD_MANAGED = ("source", "content", "header_script", "footer", "footer_script", "align")


def _seed_letter_heads(letter_heads: list, report: dict, dry_run: bool, update_content: bool = False) -> None:
	"""Crea/actualiza idempotentemente Letter Heads dedicados del catálogo (branding de propuestas).

	- Identidad: ``letter_head_name`` (autoname del DocType).
	- **NUNCA** marca ``is_default=1``: el catálogo es dueño de ``is_default=0`` para garantizar que el
	  branding se seleccione SIEMPRE de forma explícita por nombre (vía Proposal Template → Quotation),
	  nunca como default implícito del sitio. Si alguien lo marcó default, se corrige a 0.
	- Solo administra los campos provistos; el resto usa el default del DocType. No borra nada.
	"""
	for lh in letter_heads:
		name = lh["letter_head_name"]
		label = f"Letter Head '{name}'"
		expected = {k: lh[k] for k in _LETTER_HEAD_MANAGED if k in lh}
		disabled = int(lh.get("disabled", 0))

		if not frappe.db.exists("Letter Head", name):
			if not dry_run:
				doc = frappe.get_doc(
					{
						"doctype": "Letter Head",
						"letter_head_name": name,
						"is_default": 0,
						"disabled": disabled,
						**expected,
					}
				)
				doc.insert(ignore_permissions=True)
				# Letter Head.before_insert fuerza `source="Image"` (UX del DocType). Restauramos el
				# `source` del catálogo con db_set (sin re-validar): es IRRELEVANTE para el render
				# —get_letter_head lee `content` directamente, sin mirar `source`— pero necesario para
				# la idempotencia y para que un `save` posterior no dispare set_image sobre el content.
				if expected.get("source"):
					doc.db_set("source", expected["source"], update_modified=False)
			report["created"].append(label)
			continue

		current = (
			frappe.db.get_value(
				"Letter Head", name, [*expected.keys(), "is_default", "disabled"], as_dict=True
			)
			or {}
		)
		diffs = _diff(expected, current)
		flag_diffs = []
		if int(current.get("is_default") or 0) != 0:
			flag_diffs.append("is_default→0")
		if int(current.get("disabled") or 0) != disabled:
			flag_diffs.append(f"disabled→{disabled}")
		if flag_diffs:
			diffs = (diffs + ", " if diffs else "") + ", ".join(flag_diffs)

		if not diffs:
			report["unchanged"].append(label)
		elif update_content:
			if not dry_run:
				doc = frappe.get_doc("Letter Head", name)
				for k, v in expected.items():
					setattr(doc, k, v)
				doc.is_default = 0
				doc.disabled = disabled
				doc.save(ignore_permissions=True)
			report["updated"].append(label)
		else:
			report["conflicts"].append(f"{label}: difiere del catálogo → {diffs} (usar update_content)")


def _seed_print_formats(
	pfs: list,
	catalog_dir: str,
	report: dict,
	dry_run: bool,
	update_content: bool = False,
	superseded: set | None = None,
) -> None:
	"""Crea/actualiza idempotentemente Print Formats como assets administrados por el catálogo
	(capacidad genérica). Identidad: name.

	- El HTML (Jinja) y el CSS viven en archivos externos referenciados por `html_file`/`css_file`
	  (rutas relativas al JSON del catálogo); se leen y componen aquí. El `html` final autocontiene
	  el `<style>` (robusto en wkhtmltopdf) y el `css` field se conserva por compatibilidad.
	- Nunca toca los Print Formats PROTEGIDOS (assets del repo público); si el catálogo intenta
	  administrar uno, se reporta como conflicto y se omite.
	- Solo administra los campos provistos por el spec; el resto usa el default del DocType.
	- **A.2:** para un formato listado como `supersedes` en `print_format_versions` (conjunto
	  ``superseded``), NO gestiona ``disabled``: su dueño exclusivo es ``_seed_print_format_versions``.
	  Evita el flip-flop del flag entre ambos seeders (idempotencia).
	- **B:** nunca cambia el CONTENIDO/presentación de un formato ya **histórico**; si el catálogo lo
	  intentara, se reporta como **conflict** desde el dry-run (antes de que ADR-0011 lo bloquee en el
	  ``save`` del apply). ``disabled`` no es presentación → sí se permite.
	"""
	from erpnext_proposals.erpnext_proposals.utils.print_format_protection import (
		_PRESENTATION_FIELDS,
		is_print_format_historical,
	)

	superseded = superseded or set()
	fields = list(_PRINT_FORMAT_MANAGED_FIELDS)
	for pf in pfs:
		name = pf["name"]
		label = f"Print Format '{name}'"
		if name in PROTECTED_PRINT_FORMATS:
			report["conflicts"].append(f"{label}: PROTEGIDO — el loader nunca lo crea ni modifica")
			continue

		spec = _resolve_print_format_spec(pf, catalog_dir)
		# A.2: para un formato sustituido, el versionador es el ÚNICO dueño de `disabled`.
		managed = [f for f in fields if not (f == "disabled" and name in superseded)]
		provided = {f: spec.get(f) for f in managed if spec.get(f) is not None}
		if not frappe.db.exists("Print Format", name):
			if not dry_run:
				doc = {"doctype": "Print Format", "name": name}
				doc.update(provided)
				frappe.get_doc(doc).insert(ignore_permissions=True)
			report["created"].append(label)
			continue

		current = (
			frappe.db.get_value("Print Format", name, list(provided.keys()), as_dict=True) if provided else {}
		)
		diffs = _diff(provided, current)
		if not diffs:
			report["unchanged"].append(label)
			continue
		# B: un formato ya HISTÓRICO no puede cambiar su presentación/contenido (ADR-0011). Se detecta
		# aquí como CONFLICT (visible en --dry-run) en vez de reventar en `doc.save()` durante el --apply.
		# `disabled` NO es presentación (no está en _PRESENTATION_FIELDS) → no cae en este guard.
		if is_print_format_historical(name):
			presentation = sorted(
				{k for k in provided if _norm(provided.get(k)) != _norm((current or {}).get(k))}
				& set(_PRESENTATION_FIELDS)
			)
			if presentation:
				report["conflicts"].append(
					f"{label}: cambiaría la presentación de un formato HISTÓRICO ({', '.join(presentation)}) — "
					"prohibido por ADR-0011; crea una versión nueva del formato"
				)
				continue
		if update_content:
			if not dry_run:
				doc = frappe.get_doc("Print Format", name)
				for f, v in provided.items():
					doc.set(f, v)
				doc.save(ignore_permissions=True)
			report["updated"].append(f"{label}: {diffs}")
		else:
			report["conflicts"].append(f"{label}: {diffs} (usar update_content)")


def _resolve_print_format_spec(pf: dict, catalog_dir: str) -> dict:
	"""Normaliza un spec de Print Format del catálogo: lee html_file/css_file (relativos al
	catálogo), compone el html autocontenido con `<style>` y aplica defaults sensatos para un
	formato administrado por BD (standard='No', custom_format=1, page_number='Hide')."""
	spec = dict(pf)
	html_body = (
		_read_asset(os.path.join(catalog_dir, pf["html_file"])) if pf.get("html_file") else pf.get("html", "")
	)
	css = _read_asset(os.path.join(catalog_dir, pf["css_file"])) if pf.get("css_file") else pf.get("css", "")

	spec["html"] = f"<style>\n{css}\n</style>\n{html_body}" if css else html_body
	spec["css"] = css
	spec.setdefault("doc_type", "Quotation")
	spec.setdefault("print_format_type", "Jinja")
	spec.setdefault("standard", "No")
	spec.setdefault("custom_format", 1)
	spec.setdefault("page_number", "Hide")
	for k in ("html_file", "css_file", "name"):
		spec.pop(k, None)
	return spec


def _read_asset(path: str) -> str:
	"""Lee un asset de texto (HTML/CSS) referenciado por el catálogo. Ruta provista por el operador
	vía el JSON del catálogo (no es entrada de usuario final)."""
	if not os.path.exists(path):
		frappe.throw(_("No se encontró el asset referenciado por el catálogo: {0}").format(path))
	with open(path, encoding="utf-8") as fh:  # nosemgrep — lectura local del asset del catálogo
		return fh.read()


def _seed_print_format_versions(
	versions: list, catalog_dir: str, report: dict, dry_run: bool, declared: set | None = None
) -> None:
	"""Versionamiento genérico y declarativo de Print Formats (idempotente; no destructivo).

	Cada entrada declara un formato vigente `current` (que DEBE haber creado ``_seed_print_formats``)
	que SUSTITUYE a `supersedes`. Para cada una, de forma idempotente:

	1. **Deshabilita** `supersedes` (``disabled=1``) si `disable_superseded` — por la vía normal
	   ``doc.save()``. ADR-0011 permite `disabled` en un formato histórico (no forma parte de la
	   representación histórica); su HTML/CSS/nombre NUNCA se tocan. No deshabilita PROTEGIDOS.
	2. **Adjunta** el `changelog_file` como ``File`` PRIVADO al `current` (mecanismo estándar de Frappe,
	   sin Custom Fields), solo si no está ya adjunto.
	3. **Repunta** cada `template` de `supersedes` → `current` (solo si aún apunta al anterior/vacío).

	No crea el Print Format nuevo (eso es `print_formats`) ni borra nada.
	"""
	declared = declared or set()
	for v in versions:
		current = v["current"]
		supersedes = v.get("supersedes")
		label = f"Print Format version '{current}'"

		# En dry-run el formato vigente aún no está creado (print_formats no persiste); si está declarado
		# en 'print_formats' se dará por existente para reportar el plan real, no un falso conflicto.
		current_exists = bool(frappe.db.exists("Print Format", current)) or (dry_run and current in declared)
		if not current_exists:
			report["conflicts"].append(
				f"{label}: el formato vigente no existe (debe declararse en 'print_formats')"
			)
			continue

		# 1) Deshabilitar el formato sustituido (vía normal; ADR-0011 permite `disabled` en históricos).
		if supersedes and v.get("disable_superseded"):
			if supersedes in PROTECTED_PRINT_FORMATS:
				report["conflicts"].append(f"{label}: '{supersedes}' es PROTEGIDO — no se deshabilita")
			elif not frappe.db.exists("Print Format", supersedes):
				report["conflicts"].append(f"{label}: el formato sustituido '{supersedes}' no existe")
			elif frappe.db.get_value("Print Format", supersedes, "disabled"):
				report["unchanged"].append(f"{label}: '{supersedes}' ya está disabled")
			else:
				if not dry_run:
					sup = frappe.get_doc("Print Format", supersedes)
					sup.disabled = 1
					sup.save(ignore_permissions=True)
				report["updated"].append(f"{label}: '{supersedes}' → disabled=1")

		# 2) Adjuntar el changelog como File privado al formato vigente (idempotente por prefijo).
		changelog = v.get("changelog_file")
		if changelog:
			fname = os.path.basename(changelog)
			stem = os.path.splitext(fname)[0]
			already = frappe.db.exists(
				"File",
				{
					"attached_to_doctype": "Print Format",
					"attached_to_name": current,
					"file_name": ["like", f"{stem}%"],
				},
			)
			if already:
				report["unchanged"].append(f"{label}: changelog ya adjunto")
			else:
				if not dry_run:
					from frappe.utils.file_manager import save_file

					content = _read_asset(os.path.join(catalog_dir, changelog))
					save_file(fname, content, "Print Format", current, is_private=1)
				report["created"].append(f"{label}: changelog adjunto ({fname})")

		# 3) Repuntar los Proposal Templates administrados por el pack.
		for tname in v.get("templates", []):
			if not frappe.db.exists("Proposal Template", tname):
				report["conflicts"].append(f"{label}: Proposal Template '{tname}' no existe")
				continue
			cur_pf = frappe.db.get_value("Proposal Template", tname, "print_format")
			if cur_pf == current:
				report["unchanged"].append(f"{label}: template '{tname}' ya apunta al vigente")
			elif not cur_pf or cur_pf == supersedes:
				if not dry_run:
					frappe.db.set_value("Proposal Template", tname, "print_format", current)
				report["updated"].append(f"{label}: template '{tname}' → '{current}'")
			else:
				report["conflicts"].append(
					f"{label}: template '{tname}' apunta a '{cur_pf}' (ni vigente ni sustituido) — no se repunta"
				)


# ─────────────────────────────────────────────────────────────────────────────
# Vaciado explícito de campos (`clear_fields`) — genérico, opt-in, idempotente
# ─────────────────────────────────────────────────────────────────────────────

# Tipos de catálogo sobre los que un objeto puede declarar `clear_fields`.
# clave del catálogo -> (DocType, campo identidad del objeto).
# Solo tipos EDITORIALES/de presentación que el pack aún gestiona. Templates, Scope Items y Phases se
# administran en Desk: el pack no vacía sus campos (dejaría de ser el pack una fuente de escritura).
_CLEARABLE_TYPES = {
	"sections": ("Proposal Section", "section_name"),
	"items": ("Item", "item_code"),
	"letter_heads": ("Letter Head", "letter_head_name"),
}

# Campos que NUNCA pueden vaciarse por `clear_fields` (estructura/sistema/nested-set/child).
_CLEAR_FIELDS_FORBIDDEN = {
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
	"doctype",
	"lft",
	"rgt",
	"is_group",
}


def _seed_clear_fields(
	data: dict, section_remap: dict, report: dict, dry_run: bool, update_content: bool
) -> None:
	"""Vacía campos que un objeto del catálogo declare explícitamente en ``clear_fields``.

	Opt-in y genérico: la AUSENCIA de un campo en el JSON nunca se interpreta como "bórralo"; solo se
	vacía lo declarado. Idempotente: si el campo ya está vacío no hay cambio. Respeta ``update_content``
	(sin él, un vaciado pendiente se reporta como conflicto) y ``dry_run`` (no escribe pero reporta
	``updated``). Valida que el campo exista, no sea obligatorio, no sea de sistema/estructura ni una
	tabla hija. No afecta catálogos que no usen ``clear_fields``."""
	for key, (doctype, id_field) in _CLEARABLE_TYPES.items():
		for obj in data.get(key, []) or []:
			fields = obj.get("clear_fields")
			if not fields:
				continue
			ident = obj.get(id_field)
			if key == "sections":
				ident = section_remap.get(ident, ident)  # respeta el remap de secciones versionadas
			if not ident or not frappe.db.exists(doctype, ident):
				continue  # el objeto aún no existe: no hay nada que vaciar
			label = f"{doctype} '{ident}'"
			meta = frappe.get_meta(doctype)
			to_clear = []
			for f in fields:
				# Campos de sistema/estructura (`name`, `lft`, `parent`, …): protegidos SIEMPRE, incluso
				# si no aparecen como DocField normal (`meta.get_field` los devuelve como None).
				if f in _CLEAR_FIELDS_FORBIDDEN:
					report["conflicts"].append(f"{label}: clear_fields campo protegido '{f}'")
					continue
				df = meta.get_field(f)
				if not df:
					report["conflicts"].append(f"{label}: clear_fields campo inexistente '{f}'")
					continue
				if df.fieldtype in ("Table", "Table MultiSelect") or df.reqd:
					report["conflicts"].append(f"{label}: clear_fields campo no permitido '{f}'")
					continue
				if frappe.db.get_value(doctype, ident, f):  # solo si tiene valor no vacío
					to_clear.append(f)
			if not to_clear:
				continue  # ya vacíos → idempotente (no se reporta cambio)
			if not update_content:
				report["conflicts"].append(
					f"{label}: clear_fields {to_clear} pendientes (usar update_content)"
				)
				continue
			if not dry_run:
				doc = frappe.get_doc(doctype, ident)
				for f in to_clear:
					doc.set(f, None)
				doc.save(ignore_permissions=True)
			report["updated"].append(f"{label}: clear_fields {to_clear}")


def _managed_fields(record: dict, fields: list) -> tuple[dict, set]:
	"""Separa los campos administrados que el catálogo trae como CLAVE PRESENTE:

	- provided: clave presente con valor no-None (se fija ese valor);
	- cleared:  clave presente con valor null   (se limpia explícitamente).

	Una clave AUSENTE no se administra (conserva valor/default). Esto permite al catálogo
	distinguir 'no tocar este campo' (omitir) de 'ponerlo en null' (p.ej. erpnext_item=null)."""
	managed = [f for f in fields if f in record]
	provided = {f: record[f] for f in managed if record[f] is not None}
	cleared = {f for f in managed if record[f] is None}
	return provided, cleared


def _diff_managed(provided: dict, cleared: set, current: dict) -> str:
	"""Diff que contempla limpiezas explícitas: un campo en 'cleared' difiere si su valor actual
	no está vacío. Devuelve '' si no hay diferencias."""
	parts = []
	cur = current or {}
	for k, v in provided.items():
		if _norm(v) != _norm(cur.get(k)):
			parts.append(k)
	for k in sorted(cleared):
		if _norm(cur.get(k)) != "":
			parts.append(f"{k}→null")
	return ", ".join(parts)


def _diff(expected: dict, current: dict) -> str:
	"""Devuelve una descripción de los campos que difieren, o '' si son iguales."""
	parts = []
	for k, v in expected.items():
		cur = (current or {}).get(k)
		if _norm(v) != _norm(cur):
			parts.append(k)
	return ", ".join(parts)


def _norm(v) -> str:
	if v is None:
		return ""
	if isinstance(v, (int, float)):
		return str(int(v))
	return str(v).strip()


def _load_catalog(catalog_path: str | None = None) -> dict:
	path = catalog_path or SAMPLE_CATALOG
	if not os.path.exists(path):
		frappe.throw(_("No se encontró el archivo de catálogo: {0}").format(path))
	# catalog_path lo provee el operador vía `bench execute` (no es entrada de usuario final);
	# el loader no está whitelisted. Lectura local de solo lectura del JSON de catálogo.
	with open(path, encoding="utf-8") as fh:  # nosemgrep
		return json.load(fh)


def _as_bool(v) -> bool:
	if isinstance(v, bool):
		return v
	if v is None:
		return True
	return str(v).strip().lower() not in ("false", "0", "no", "n", "")


def _print_report(report: dict, dry_run: bool, data: dict) -> None:
	mode = "DRY-RUN (sin cambios en BD)" if dry_run else "CARGA REAL (commit)"
	lines = [
		"",
		"=" * 70,
		f"  Catálogo {data.get('catalog', '')} v{data.get('version', '?')} — {mode}",
		f"  Site: {frappe.local.site}",
		"=" * 70,
		f"  Creados:      {len(report['created'])}",
		f"  Sin cambios:  {len(report['unchanged'])}",
		f"  Actualizados: {len(report['updated'])}",
		f"  Reutilizados: {len(report['reused'])}",
		f"  Pendientes:   {len(report.get('pending', []))}",
		f"  Conflictos:   {len(report['conflicts'])}",
		"-" * 70,
	]
	for bucket, title in (
		("created", "CREADOS"),
		("updated", "ACTUALIZADOS (contenido del catálogo)"),
		("pending", "PENDIENTES (erpnext_item / dependencias sin resolver — se completan al re-ejecutar)"),
		("conflicts", "CONFLICTOS (revisar — NO se modificaron)"),
	):
		if report.get(bucket):
			lines.append(f"  {title}:")
			lines.extend(f"    · {x}" for x in report[bucket])
			lines.append("-" * 70)
	if dry_run and not report["conflicts"]:
		lines.append("  Dry-run OK. Para cargar: --kwargs \"{'dry_run': False}\"")
	if report["conflicts"]:
		lines.append("  ⚠️  Hay conflictos: revisa antes de cargar. El seeder no sobrescribe.")
	lines.append("=" * 70)
	print("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════════════
# v13: seeders funcionales reactivados (recuperados de 20434dc^) + Items org./Email Templates
# ═══════════════════════════════════════════════════════════════════════════


def _seed_scope_items(items: list, report: dict, dry_run: bool, update_content: bool = False) -> None:
	fields = [
		"title",
		"sequence",
		"phase",
		"erpnext_item",
		"estimated_hours",
		"default_assignee",
		"default_designation",
		"visible_in_proposal",
		"is_internal_cost_task",
		"description",
		"deliverable",
		# Planeación PMO (opcional): reglas reutilizables del catálogo.
		"planned_start_offset_days",
		# Momento relativo de ejecución del programa fuente (texto libre; opcional).
		"moment",
		"planned_duration_days",
		"is_milestone",
	]
	for it in items:
		code = it["code"]
		label = f"Scope Item '{code}'"
		# Fail-closed del Responsable de ejecución: si el catálogo trae default_assignee y el User no
		# existe / está deshabilitado en el site destino, NO se crea/actualiza el Scope Item (se reporta
		# como conflicto; nunca se inventa usuario ni se ignora el error).
		_assignee = it.get("default_assignee")
		if _assignee and (
			not frappe.db.exists("User", _assignee) or not frappe.db.get_value("User", _assignee, "enabled")
		):
			report["conflicts"].append(
				f"{label}: default_assignee {_assignee!r} no existe o está deshabilitado en el site — fail-closed"
			)
			continue
		# Campos administrados = los que el catálogo trae como clave presente. Se distingue:
		#   - provided: clave presente con valor no-None  → se fija ese valor;
		#   - cleared:  clave presente con valor null      → se LIMPIA (p.ej. erpnext_item=null
		#                                                     para que NO autogenere con el Item).
		# Un campo OMITIDO (clave ausente) no se administra: conserva su valor / default del modelo
		# (así estimated_hours omitido no marca falso conflicto contra el 0.0 del modelo).
		provided, cleared = _managed_fields(it, fields)
		# erpnext_item PENDIENTE: el catálogo lo provee pero el Item comercial aún no existe. No se
		# fuerza el Link (fallaría). Se deja sin vincular y se registra; al re-ejecutar la
		# sincronización cuando el Item exista, el Link se completa (identidad por `code`, sin duplicar).
		pending_item = provided.get("erpnext_item")
		if pending_item and not frappe.db.exists("Item", pending_item):
			provided.pop("erpnext_item")
			report["pending"].append(
				f"{label}: Item '{pending_item}' no existe aún — erpnext_item pendiente (se vinculará al re-ejecutar)"
			)
		keys = list(provided.keys()) + list(cleared)

		# Relación N:N Item ↔ Scope Item (child table `erpnext_items`). Se administra SOLO si la clave
		# está presente en el registro: clave AUSENTE = no tocar (conserva lo existente); lista = sincroniza
		# exactamente (agrega faltantes, quita no declarados, sin duplicar, orden irrelevante); lista vacía
		# = limpia. Es INDEPENDIENTE del Link legacy `erpnext_item`: no se sincroniza ni se hace backfill
		# entre ambos. Items inexistentes se OMITEN y se reportan (mismo criterio que dependencias/legacy;
		# no se crean Items implícitos). Un Item repetido en el JSON invalida el catálogo.
		has_n2m = "erpnext_items" in it
		desired_items: list = []
		if has_n2m:
			raw = list(it.get("erpnext_items") or [])
			if len(raw) != len(set(raw)):
				frappe.throw(
					_("Catálogo inválido: 'erpnext_items' repite un Item en Scope Item '{0}'.").format(code)
				)
			desired_items = [i for i in raw if frappe.db.exists("Item", i)]
			for miss in [i for i in raw if not frappe.db.exists("Item", i)]:
				report["pending"].append(
					f"{label}: Item '{miss}' no existe aún — relación erpnext_items pendiente (se vinculará al re-ejecutar)"
				)

		if not frappe.db.exists("Scope Item", code):
			if not dry_run:
				doc = {"doctype": "Scope Item", "code": code, "enabled": 1}
				doc.update(provided)
				for f in cleared:
					doc[f] = None
				if has_n2m:
					doc["erpnext_items"] = [{"item": i} for i in desired_items]
				frappe.get_doc(doc).insert(ignore_permissions=True)
			report["created"].append(label)
			continue

		current = frappe.db.get_value("Scope Item", code, keys, as_dict=True) if keys else {}
		diff_parts = []
		scalar_diffs = _diff_managed(provided, cleared, current)
		if scalar_diffs:
			diff_parts.append(scalar_diffs)
		if has_n2m:
			current_items = set(
				frappe.get_all(
					"Scope Item ERPNext Item",
					filters={"parenttype": "Scope Item", "parentfield": "erpnext_items", "parent": code},
					pluck="item",
				)
			)
			if set(desired_items) != current_items:
				diff_parts.append(f"erpnext_items {sorted(current_items)} -> {sorted(desired_items)}")

		if not diff_parts:
			report["unchanged"].append(label)
		elif update_content:
			if not dry_run:
				doc = frappe.get_doc("Scope Item", code)
				for f, v in provided.items():
					doc.set(f, v)
				for f in cleared:
					doc.set(f, None)
				if has_n2m:
					doc.set("erpnext_items", [{"item": i} for i in desired_items])
				doc.save(ignore_permissions=True)
			report["updated"].append(f"{label}: {', '.join(diff_parts)}")
		else:
			report["conflicts"].append(f"{label}: {', '.join(diff_parts)}")

	# 2º paso idempotente: dependencias del catálogo (todos los Scope Items ya existen).
	_seed_scope_dependencies(items, report, dry_run, update_content)


def _seed_scope_dependencies(items: list, report: dict, dry_run: bool, update_content: bool = False) -> None:
	"""Aplica `depends_on` (lista de códigos de Scope Items predecesores) como filas de la child table
	`depends_on_scope_items`. Segundo paso: se ejecuta tras crear todos los Scope Items del catálogo.

	- Idempotente: identidad por conjunto de códigos; si el conjunto ya coincide, no escribe.
	- Clave `depends_on` AUSENTE → no administra dependencias (conserva lo existente).
	- Predecesores que no existen (p. ej. de un Item no contratado) se OMITEN y se reportan; nunca
	  se crea un Link roto. Auto-referencia/duplicados/ciclos los valida Scope Item.validate().
	"""
	for it in items:
		if "depends_on" not in it:
			continue
		code = it["code"]
		desired = [c for c in (it.get("depends_on") or []) if c]
		if not frappe.db.exists("Scope Item", code):
			# dry-run sobre un Scope Item aún no creado: se reportaría en la próxima corrida real.
			if desired and dry_run:
				report["updated"].append(
					f"Scope Item '{code}': {len(desired)} dependencia(s) (pendiente de creación)"
				)
			continue

		valid = [c for c in desired if frappe.db.exists("Scope Item", c)]
		missing = [c for c in desired if not frappe.db.exists("Scope Item", c)]
		if missing:
			report["pending"].append(
				f"Scope Item '{code}': dependencias omitidas (Scope Items inexistentes) {missing}"
			)

		current = set(
			frappe.get_all(
				"Scope Item Dependency",
				filters={
					"parenttype": "Scope Item",
					"parentfield": "depends_on_scope_items",
					"parent": code,
				},
				pluck="depends_on",
			)
		)
		if set(valid) == current:
			continue  # ya coincide — idempotente, sin escritura

		if not (update_content or not current):
			# Existe y difiere pero sin update_content: no sobrescribir, reportar conflicto.
			report["conflicts"].append(
				f"Scope Item '{code}': dependencias difieren del catálogo {sorted(valid)} vs {sorted(current)} (usar update_content)"
			)
			continue

		if not dry_run:
			doc = frappe.get_doc("Scope Item", code)
			doc.set("depends_on_scope_items", [])
			for dep in valid:
				doc.append("depends_on_scope_items", {"depends_on": dep})
			doc.save(ignore_permissions=True)
		report["updated"].append(f"Scope Item '{code}': dependencias {sorted(valid)}")


def _seed_templates(
	templates: list, section_remap: dict, report: dict, dry_run: bool, update_content: bool
) -> None:
	# Secciones válidas para referenciar: las base/existentes + los nombres reales resueltos.
	existing = _existing_section_names()
	catalog_names = set(section_remap.values())
	valid_sections = existing | catalog_names
	reused_base: set = set()
	for t in templates:
		name = t["template_name"]
		label = f"Proposal Template '{name}'"

		# Re-mapear cada referencia de sección al nombre real (canónico o versionado).
		rows = []
		missing = []
		for r in t["sections"]:
			resolved = section_remap.get(r["proposal_section"], r["proposal_section"])
			if resolved not in valid_sections:
				missing.append(r["proposal_section"])
			elif resolved in existing and resolved not in catalog_names:
				reused_base.add(resolved)  # sección base preexistente reutilizada por el template
			row = dict(r)
			row["proposal_section"] = resolved
			rows.append(row)
		if missing:
			report["conflicts"].append(f"{label}: secciones inexistentes {missing}")
			continue

		if not frappe.db.exists("Proposal Template", name):
			if not dry_run:
				doc = frappe.get_doc(
					{
						"doctype": "Proposal Template",
						"template_name": name,
						"description": t.get("description", ""),
					}
				)
				if t.get("print_format"):
					doc.print_format = t["print_format"]
				if t.get("sow_print_format"):
					doc.sow_print_format = t["sow_print_format"]
				if t.get("letter_head"):
					doc.letter_head = t["letter_head"]
				if "separate_cover_page" in t:
					doc.separate_cover_page = int(t["separate_cover_page"])
				for r in rows:
					doc.append("sections", _template_section_row(r))
				doc.insert(ignore_permissions=True)
			report["created"].append(f"{label} ({len(rows)} secciones)")
			continue

		# Existe: comparar filas + print_format. Si difiere y update_content → reconstruir.
		diffs = _template_rows_diff(name, rows)
		if t.get("print_format"):
			pf_current = frappe.db.get_value("Proposal Template", name, "print_format") or ""
			if (t["print_format"] or "") != pf_current:
				diffs = (
					diffs + "; " if diffs else ""
				) + f"print_format: {pf_current!r} -> {t['print_format']!r}"
		if t.get("sow_print_format"):
			sow_current = frappe.db.get_value("Proposal Template", name, "sow_print_format") or ""
			if (t["sow_print_format"] or "") != sow_current:
				diffs = (
					diffs + "; " if diffs else ""
				) + f"sow_print_format: {sow_current!r} -> {t['sow_print_format']!r}"
		if t.get("letter_head"):
			lh_current = frappe.db.get_value("Proposal Template", name, "letter_head") or ""
			if (t["letter_head"] or "") != lh_current:
				diffs = (
					diffs + "; " if diffs else ""
				) + f"letter_head: {lh_current!r} -> {t['letter_head']!r}"
		if "separate_cover_page" in t:
			scp_current = int(frappe.db.get_value("Proposal Template", name, "separate_cover_page") or 0)
			if int(t["separate_cover_page"]) != scp_current:
				diffs = (
					diffs + "; " if diffs else ""
				) + f"separate_cover_page: {scp_current} -> {int(t['separate_cover_page'])}"
		if not diffs:
			report["unchanged"].append(label)
		elif update_content:
			if not dry_run:
				doc = frappe.get_doc("Proposal Template", name)
				if t.get("description"):
					doc.description = t["description"]
				if t.get("print_format"):
					doc.print_format = t["print_format"]
				if t.get("sow_print_format"):
					doc.sow_print_format = t["sow_print_format"]
				if t.get("letter_head"):
					doc.letter_head = t["letter_head"]
				if "separate_cover_page" in t:
					doc.separate_cover_page = int(t["separate_cover_page"])
				doc.set("sections", [])
				for r in rows:
					doc.append("sections", _template_section_row(r))
				doc.save(ignore_permissions=True)
			report["updated"].append(f"{label} ({len(rows)} secciones)")
		else:
			report["conflicts"].append(f"{label}: difiere del catálogo → {diffs} (usar update_content)")

	for s in sorted(reused_base):
		report["reused"].append(f"Proposal Section '{s}' (base, reutilizada)")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers


def _template_section_row(r: dict) -> dict:
	return {
		"proposal_section": r["proposal_section"],
		"sequence": r["sequence"],
		"include_by_default": r.get("include_by_default", 1),
		"use_custom_content": r.get("use_custom_content", 0),
		"custom_content": r.get("custom_content", ""),
		"custom_title": r.get("custom_title", ""),
		"hide_title": r.get("hide_title", 0),
		"page_break_before": r.get("page_break_before", 0),
	}


# ─────────────────────────────────────────────────────────────────────────────
# Vaciado explícito de campos (`clear_fields`) — genérico, opt-in, idempotente
# ─────────────────────────────────────────────────────────────────────────────

# Tipos de catálogo sobre los que un objeto puede declarar `clear_fields`.
# clave del catálogo -> (DocType, campo identidad del objeto).
_CLEARABLE_TYPES = {
	"templates": ("Proposal Template", "template_name"),
	"sections": ("Proposal Section", "section_name"),
	"scope_items": ("Scope Item", "code"),
	"items": ("Item", "item_code"),
	"phases": ("Proposal Phase", "phase_code"),
	"letter_heads": ("Letter Head", "letter_head_name"),
}

# Campos que NUNCA pueden vaciarse por `clear_fields` (estructura/sistema/nested-set/child).
_CLEAR_FIELDS_FORBIDDEN = {
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
	"doctype",
	"lft",
	"rgt",
	"is_group",
}


def _template_rows_diff(template_name: str, expected_rows: list) -> str:
	"""Compara las filas actuales del template contra el catálogo. Devuelve '' si son iguales."""
	doc = frappe.get_doc("Proposal Template", template_name)
	current = sorted(
		(
			(
				row.proposal_section,
				row.sequence,
				int(row.include_by_default or 0),
				int(row.use_custom_content or 0),
				(row.custom_title or ""),
				(row.custom_content or ""),
				int(row.hide_title or 0),
				int(row.page_break_before or 0),
			)
			for row in doc.sections
		),
		key=lambda x: x[1],
	)
	expected = sorted(
		(
			(
				r["proposal_section"],
				r["sequence"],
				int(r.get("include_by_default", 1)),
				int(r.get("use_custom_content", 0)),
				(r.get("custom_title") or ""),
				(r.get("custom_content") or ""),
				int(r.get("hide_title", 0)),
				int(r.get("page_break_before", 0)),
			)
			for r in expected_rows
		),
		key=lambda x: x[1],
	)
	if current == expected:
		return ""
	return f"{len(current)} filas actuales vs {len(expected)} del catálogo"


def _existing_section_names() -> set:
	return set(frappe.get_all("Proposal Section", pluck="name"))


# ─────────────────────────────────────────────────────────────────────────────
# v13: Items organizativos (NO vendibles/comprables/stock) + Email Templates
# ─────────────────────────────────────────────────────────────────────────────

_SUPPORT_ITEM_FIELDS = (
	"item_name",
	"item_group",
	"stock_uom",
	"is_stock_item",
	"is_sales_item",
	"is_purchase_item",
	"disabled",
)


def _seed_support_items(items: list, report: dict, dry_run: bool, update_content: bool = False) -> None:
	"""Crea/actualiza Items ORGANIZATIVOS requeridos por paquetes de alcance (p. ej. `COORD-LICENCIAS`).

	Acotado y fail-closed: solo Items NO vendibles / NO comprables / NO stock (is_sales/purchase/stock==0);
	cualquier otra cosa es un master comercial/fiscal que el loader NO crea (se reporta como conflicto).
	Requiere que el Item Group y la UOM ya existan en el site (masters que administra facturacion_mexico):
	si faltan, se reporta `pending` y se omite (nunca se crean). Idempotente por `item_code`."""
	for it in items:
		code = it["item_code"]
		label = f"Support Item '{code}'"
		if (
			int(it.get("is_sales_item", 0))
			or int(it.get("is_purchase_item", 0))
			or int(it.get("is_stock_item", 0))
		):
			report["conflicts"].append(
				f"{label}: no es organizativo (is_sales/purchase/stock deben ser 0) — el loader no crea Items comerciales/fiscales"
			)
			continue
		ig = it.get("item_group")
		uom = it.get("stock_uom")
		if not ig or not frappe.db.exists("Item Group", ig):
			report["pending"].append(
				f"{label}: Item Group {ig!r} no existe en el site (se administra fuera del pack)"
			)
			continue
		if not uom or not frappe.db.exists("UOM", uom):
			report["pending"].append(f"{label}: UOM {uom!r} no existe o no es válida en el site")
			continue
		expected = {
			"item_name": it.get("item_name") or code,
			"item_group": ig,
			"stock_uom": uom,
			"is_stock_item": 0,
			"is_sales_item": 0,
			"is_purchase_item": 0,
			"disabled": int(it.get("disabled", 0)),
		}
		if not frappe.db.exists("Item", code):
			if not dry_run:
				frappe.get_doc({"doctype": "Item", "item_code": code, **expected}).insert(
					ignore_permissions=True
				)
			report["created"].append(label)
			continue
		current = frappe.db.get_value("Item", code, list(_SUPPORT_ITEM_FIELDS), as_dict=True) or {}
		diffs = _diff(expected, current)
		if not diffs:
			report["unchanged"].append(label)
		elif update_content:
			if not dry_run:
				doc = frappe.get_doc("Item", code)
				for k, v in expected.items():
					doc.set(k, v)
				doc.save(ignore_permissions=True)
			report["updated"].append(f"{label}: {diffs}")
		else:
			report["conflicts"].append(f"{label}: {diffs} (usar update_content)")


_EMAIL_TEMPLATE_FIELDS = ("subject", "use_html", "response", "response_html", "reference_doctype")


def _seed_email_templates(ets: list, report: dict, dry_run: bool, update_content: bool = False) -> None:
	"""Crea/actualiza Email Templates nativos del flujo (p. ej. `Propuesta Ganada PMO`). Identidad: name.
	Solo administra los campos provistos; idempotente; conflictos reportados si difiere sin update_content."""
	for et in ets:
		name = et["name"]
		label = f"Email Template '{name}'"
		expected = {k: et[k] for k in _EMAIL_TEMPLATE_FIELDS if k in et}
		if not frappe.db.exists("Email Template", name):
			if not dry_run:
				frappe.get_doc({"doctype": "Email Template", "name": name, **expected}).insert(
					ignore_permissions=True
				)
			report["created"].append(label)
			continue
		current = frappe.db.get_value("Email Template", name, list(expected.keys()), as_dict=True) or {}
		diffs = _diff(expected, current)
		if not diffs:
			report["unchanged"].append(label)
		elif update_content:
			if not dry_run:
				doc = frappe.get_doc("Email Template", name)
				for k, v in expected.items():
					doc.set(k, v)
				doc.save(ignore_permissions=True)
			report["updated"].append(f"{label}: {diffs}")
		else:
			report["conflicts"].append(f"{label}: {diffs} (usar update_content)")
