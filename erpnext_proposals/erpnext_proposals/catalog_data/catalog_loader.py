"""Cargador idempotente de catálogos de propuestas (genérico, reutilizable).

Carga un catálogo (Proposal Phases, Sections, Templates, Scope Items) desde un archivo JSON
externo a la app, indicado por ruta. El JSON del catálogo NO se versiona en la app: es dato
específico de cada implementación/cliente y vive fuera del repositorio.

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
- crea únicamente lo inexistente;
- reutiliza las 10 Sections base y NO las modifica;
- NO modifica los 3 Templates genéricos;
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
LOADER_CAPS_VERSION = 10


def capabilities() -> dict:
	"""Reporta (y devuelve) las capacidades del loader / pipeline de impresión. La usa el instalador
	de producción para DETECTAR Y RECHAZAR una versión del app sin las capacidades requeridas.

	    bench --site <site> execute erpnext_proposals.erpnext_proposals.catalog_data.catalog_loader.capabilities
	"""
	from erpnext_proposals.erpnext_proposals.utils import printing

	caps = {
		"caps_version": LOADER_CAPS_VERSION,
		"items": callable(globals().get("_seed_items")),
		"scope_explicit_null": callable(globals().get("_managed_fields")),
		"print_formats": callable(globals().get("_seed_print_formats")),
		"protected_print_formats": bool(PROTECTED_PRINT_FORMATS),
		"get_logo_data_uri": callable(getattr(printing, "get_logo_data_uri", None)),
		"payment_terms": callable(globals().get("_seed_payment_terms"))
		and callable(globals().get("_seed_payment_terms_templates")),
		# v5: planeación PMO + dependencias de catálogo + erpnext_item pendiente.
		"scope_pmo_planning": callable(globals().get("_seed_scope_dependencies")),
		# v6: Designations + Skills + relación nativa Designation.skills (gate HRMS con pending).
		"designations_skills": callable(globals().get("_seed_designations"))
		and callable(globals().get("_seed_skills")),
		# v7: Tags nativos de catálogo → Proposal Phase (add-only, no destructivo).
		"phase_tags": callable(globals().get("_apply_phase_tags")),
		# v8: Versionamiento declarativo de Print Formats (deshabilitar anterior + changelog + repunte).
		"print_format_versions": callable(globals().get("_seed_print_format_versions")),
		# v9: Letter Heads dedicados (branding no-default) + Proposal Template.letter_head.
		"letter_heads": callable(globals().get("_seed_letter_heads")),
		# v10: el catálogo puede declarar el renderer profile de un Print Format (ADR-0015).
		"renderer_profile": "proposal_renderer_profile" in _PRINT_FORMAT_MANAGED_FIELDS,
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
		# Perfiles/capacidades ANTES del resto: los Scope Items pueden referenciar default_designation
		# (Link → Designation), así que las Designations deben existir primero. Orden con HRMS: Skills →
		# Designations (+ relación) → resto. Sin HRMS: Designations sí; Skills/relaciones a 'pending'.
		hrms_ok = _hrms_available()
		_seed_skills(data.get("skills", []), report, dry_run, update_content, hrms_ok)
		_seed_designations(data.get("designations", []), report, dry_run, update_content, hrms_ok)
		_seed_phases(data["phases"], report, dry_run)
		section_remap = _seed_sections(
			data["sections"], report, dry_run, update_content, set(data.get("versioned", []))
		)
		# erpnext_proposals NO crea/actualiza UOM ni Item Groups (masters fiscales de
		# facturacion_mexico): el loader simplemente no tiene esa capacidad. Los Items referencian
		# UOM/Item Groups existentes; su validez la garantizan los campos Link nativos de Frappe.
		_seed_items(data.get("items", []), report, dry_run, update_content)
		_seed_scope_items(data["scope_items"], report, dry_run, update_content)
		# Condiciones de pago corporativas (NO fiscales): Payment Terms y su Template. Los Payment
		# Terms deben existir antes de referenciarse en el Template.
		_seed_payment_terms(data.get("payment_terms", []), report, dry_run, update_content)
		_seed_payment_terms_templates(
			data.get("payment_terms_templates", []), report, dry_run, update_content
		)
		# Letter Heads dedicados antes que Templates: Proposal Template.letter_head es un Link que
		# requiere que el Letter Head exista al guardar el template. NUNCA se marcan como default.
		_seed_letter_heads(data.get("letter_heads", []), report, dry_run, update_content)
		# Print Formats antes que Templates: Proposal Template.print_format es un Link que
		# requiere que el Print Format exista al guardar el template.
		# Formatos sustituidos: el versionador es dueño de su `disabled`; _seed_print_formats no lo gestiona.
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
		_seed_templates(data["templates"], section_remap, report, dry_run, update_content)
		# Versionamiento de Print Formats: DESPUÉS de crear el formato nuevo (print_formats) y de
		# sembrar templates. Deshabilita el anterior, adjunta changelog y repunta templates.
		_seed_print_format_versions(
			data.get("print_format_versions", []),
			catalog_dir,
			report,
			dry_run,
			declared={pf.get("name") for pf in data.get("print_formats", [])},
		)
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
# Perfiles y capacidades: Designation (erpnext) + Skill (hrms) + relación nativa
# ─────────────────────────────────────────────────────────────────────────────


def _hrms_available() -> bool:
	"""True si existe la estructura nativa de HRMS para Skills y su relación con Designation:
	DocType 'Skill', DocType 'Designation Skill' y el campo child 'skills' en Designation (que HRMS
	agrega por setup.py). Sin ella, las Skills y relaciones se posponen ('pending')."""
	if not (frappe.db.exists("DocType", "Skill") and frappe.db.exists("DocType", "Designation Skill")):
		return False
	return bool(frappe.get_meta("Designation").has_field("skills"))


def _seed_skills(skills: list, report: dict, dry_run: bool, update_content: bool, hrms_ok: bool) -> None:
	"""Crea/conserva idempotentemente Skills (HRMS). Identidad: skill_name. No sobrescribe la
	descripción existente salvo update_content; reporta diferencias como conflicto. Sin HRMS → pending."""
	if not skills:
		return
	if not hrms_ok:
		for s in skills:
			report["pending"].append(
				f"Skill '{_require(s, 'skill_name')}': HRMS no instalado — pendiente (se creará al re-ejecutar)"
			)
		return
	for s in skills:
		name = _require(s, "skill_name")
		label = f"Skill '{name}'"
		provided = {"description": s["description"]} if s.get("description") is not None else {}
		if not frappe.db.exists("Skill", name):
			if not dry_run:
				doc = {"doctype": "Skill", "skill_name": name}
				doc.update(provided)
				frappe.get_doc(doc).insert(ignore_permissions=True)
			report["created"].append(label)
			continue
		current = frappe.db.get_value("Skill", name, list(provided.keys()), as_dict=True) if provided else {}
		diffs = _diff(provided, current)
		if not diffs:
			report["unchanged"].append(label)
		elif update_content:
			if not dry_run:
				doc = frappe.get_doc("Skill", name)
				for f, v in provided.items():
					doc.set(f, v)
				doc.save(ignore_permissions=True)
			report["updated"].append(f"{label}: {diffs}")
		else:
			report["conflicts"].append(f"{label}: {diffs} (no se sobrescribe; usar update_content)")


def _seed_designations(
	designations: list, report: dict, dry_run: bool, update_content: bool, hrms_ok: bool
) -> None:
	"""Crea/conserva idempotentemente Designations (erpnext). Identidad: designation_name. No
	sobrescribe la descripción existente salvo update_content; reporta diferencias. La lista opcional
	`skills` (nombres exactos) se aplica como relación nativa Designation.skills (solo con HRMS)."""
	if not designations:
		return
	for d in designations:
		name = _require(d, "designation_name")
		label = f"Designation '{name}'"
		provided = {"description": d["description"]} if d.get("description") is not None else {}
		if not frappe.db.exists("Designation", name):
			if not dry_run:
				doc = {"doctype": "Designation", "designation_name": name}
				doc.update(provided)
				frappe.get_doc(doc).insert(ignore_permissions=True)
			report["created"].append(label)
		else:
			current = (
				frappe.db.get_value("Designation", name, list(provided.keys()), as_dict=True)
				if provided
				else {}
			)
			diffs = _diff(provided, current)
			if not diffs:
				report["unchanged"].append(label)
			elif update_content:
				if not dry_run:
					doc = frappe.get_doc("Designation", name)
					for f, v in provided.items():
						doc.set(f, v)
					doc.save(ignore_permissions=True)
				report["updated"].append(f"{label}: {diffs}")
			else:
				report["conflicts"].append(f"{label}: {diffs} (no se sobrescribe; usar update_content)")

		if "skills" in d:
			_apply_designation_skills(name, d.get("skills") or [], report, dry_run, hrms_ok)


def _apply_designation_skills(
	designation: str, skill_names: list, report: dict, dry_run: bool, hrms_ok: bool
) -> None:
	"""Aplica la relación nativa Designation.skills (child 'Designation Skill', Link 'skill').

	- Solo AGREGA Skills faltantes (comparación por nombre exacto); nunca duplica ni elimina filas
	  existentes que no estén en el catálogo. Sin niveles ni evaluaciones.
	- Sin HRMS, o si alguna Skill referenciada aún no existe, la relación (o esa parte) queda 'pending'.
	"""
	label = f"Designation '{designation}' skills"
	desired = [s for s in skill_names if s]
	if not desired:
		return
	if not hrms_ok:
		report["pending"].append(f"{label}: HRMS no instalado — relación pendiente {sorted(desired)}")
		return

	missing = [s for s in desired if not frappe.db.exists("Skill", s)]
	valid = [s for s in desired if frappe.db.exists("Skill", s)]
	if missing:
		report["pending"].append(f"{label}: Skills inexistentes {sorted(missing)} — relación pendiente")

	if not frappe.db.exists("Designation", designation):
		if valid and dry_run:  # dry-run: la Designation aún no existe pero se crearía
			report["updated"].append(f"{label}: agregaría {sorted(valid)} (pendiente de creación)")
		return

	current = set(
		frappe.get_all(
			"Designation Skill",
			filters={"parenttype": "Designation", "parentfield": "skills", "parent": designation},
			pluck="skill",
		)
	)
	to_add = [s for s in valid if s not in current]
	if not to_add:
		return  # relación ya presente — idempotente, sin ruido
	if not dry_run:
		doc = frappe.get_doc("Designation", designation)
		for s in to_add:
			doc.append("skills", {"skill": s})
		doc.save(ignore_permissions=True)
	report["updated"].append(f"{label}: +{sorted(to_add)}")


def _require(record: dict, key: str):
	"""Devuelve record[key] o detiene la carga (rollback) si falta la clave de identidad."""
	value = record.get(key)
	if not value:
		frappe.throw(_("El catálogo tiene un registro sin '{0}' obligatorio: {1}").format(key, record))
	return value


# ─────────────────────────────────────────────────────────────────────────────
# Seeders por DocType
# ─────────────────────────────────────────────────────────────────────────────


def _seed_phases(phases: list, report: dict, dry_run: bool) -> None:
	for p in phases:
		code = p["phase_code"]
		label = f"Proposal Phase '{code}'"
		if not frappe.db.exists("Proposal Phase", code):
			if not dry_run:
				frappe.get_doc(
					{
						"doctype": "Proposal Phase",
						"phase_code": code,
						"phase_name": p["phase_name"],
						"sequence": p["sequence"],
						"enabled": 1,
					}
				).insert(ignore_permissions=True)
			report["created"].append(label)
		else:
			current = frappe.db.get_value("Proposal Phase", code, ["phase_name", "sequence"], as_dict=True)
			diffs = _diff({"phase_name": p["phase_name"], "sequence": p["sequence"]}, current)
			if diffs:
				report["conflicts"].append(f"{label}: {diffs}")
			else:
				report["unchanged"].append(label)
		# Tags nativos del catálogo (clasificación de la línea) → Proposal Phase, add-only.
		_apply_phase_tags(code, p.get("tags"), report, dry_run)


def _apply_phase_tags(code: str, tags: list, report: dict, dry_run: bool) -> None:
	"""Aplica los Tags NATIVOS de Frappe declarados en el catálogo a una Proposal Phase.

	Capacidad estándar de Frappe (``DocTags``), genérica (no conoce nombres de Tags ni códigos de
	línea) e idempotente. **No destructiva**: solo AGREGA los Tags del catálogo que falten; nunca
	elimina Tags ajenos/no administrados de la Proposal Phase. Estos Tags son la fuente que la app
	propaga a la Task-fase padre al crear el Project (ver utils/project._copy_native_tags).
	"""
	from frappe.desk.doctype.tag.tag import DocTags

	wanted = [str(t).strip() for t in (tags or []) if t and str(t).strip()]
	if not wanted:
		return
	dt = DocTags("Proposal Phase")
	current = (
		{t for t in dt.get_tags(code).split(",") if t} if frappe.db.exists("Proposal Phase", code) else set()
	)
	missing = [t for t in wanted if t not in current]
	if not missing:
		return
	if not dry_run:
		for t in missing:
			dt.add(code, t)
	report["updated"].append(f"Proposal Phase '{code}': +tags {missing}")


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
	"""Crea/actualiza idempotentemente ERPNext Items (capacidad genérica). Identidad: item_code.
	Los datos concretos (nombres, grupos, descripciones) viven en el catálogo externo, no en el app.
	Solo se comparan/actualizan los campos que el catálogo provee (no se fuerzan vacíos)."""
	fields = [
		"item_name",
		"item_group",
		"stock_uom",
		"is_stock_item",
		"is_sales_item",
		"description",
		# Contenido general de la propuesta (Text Editor). Se administran igual que el resto:
		# clave presente fija el valor, null explícito limpia, clave ausente no toca.
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
			if not dry_run:
				doc = {"doctype": "Item", "item_code": code}
				doc.update(provided)
				for f in cleared:
					doc[f] = None
				frappe.get_doc(doc).insert(ignore_permissions=True)
			report["created"].append(label)
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


def _seed_payment_terms(terms: list, report: dict, dry_run: bool, update_content: bool = False) -> None:
	"""Crea/actualiza idempotentemente Payment Terms (condiciones de pago corporativas, NO fiscales).
	Identidad: payment_term_name. Solo administra los campos provistos por el catálogo."""
	fields = ["invoice_portion", "description", "due_date_based_on", "credit_days", "credit_months"]
	for t in terms:
		name = t["payment_term_name"]
		label = f"Payment Term '{name}'"
		provided = {f: t[f] for f in fields if f in t and t[f] is not None}
		if not frappe.db.exists("Payment Term", name):
			if not dry_run:
				doc = {"doctype": "Payment Term", "payment_term_name": name}
				doc.update(provided)
				frappe.get_doc(doc).insert(ignore_permissions=True)
			report["created"].append(label)
			continue
		current = (
			frappe.db.get_value("Payment Term", name, list(provided.keys()), as_dict=True) if provided else {}
		)
		diffs = _diff(provided, current)
		if not diffs:
			report["unchanged"].append(label)
		elif update_content:
			if not dry_run:
				doc = frappe.get_doc("Payment Term", name)
				for f, v in provided.items():
					doc.set(f, v)
				doc.save(ignore_permissions=True)
			report["updated"].append(f"{label}: {diffs}")
		else:
			report["conflicts"].append(f"{label}: {diffs}")


def _pt_template_row(r: dict) -> dict:
	return {
		"payment_term": r.get("payment_term"),
		"invoice_portion": r.get("invoice_portion"),
		"description": r.get("description", ""),
		"due_date_based_on": r.get("due_date_based_on", "Day(s) after invoice date"),
		"credit_days": r.get("credit_days", 0),
	}


def _pt_template_diff(name: str, rows: list) -> str:
	"""Compara las filas actuales del Payment Terms Template contra el catálogo (payment_term +
	invoice_portion). Devuelve '' si son iguales."""
	doc = frappe.get_doc("Payment Terms Template", name)
	current = sorted(
		(
			row.payment_term,
			float(row.invoice_portion or 0),
			int(row.credit_days or 0),
			row.due_date_based_on or "",
		)
		for row in doc.terms
	)
	expected = sorted(
		(
			r.get("payment_term"),
			float(r.get("invoice_portion") or 0),
			int(r.get("credit_days") or 0),
			r.get("due_date_based_on") or "Day(s) after invoice date",
		)
		for r in rows
	)
	return (
		""
		if current == expected
		else f"{len(current)} términos actuales vs {len(expected)} del catálogo (o difieren)"
	)


def _seed_payment_terms_templates(
	templates: list, report: dict, dry_run: bool, update_content: bool = False
) -> None:
	"""Crea/actualiza idempotentemente Payment Terms Templates. Identidad: template_name.
	El calendario real de cada Quotation lo genera ERPNext a partir de esta plantilla."""
	for t in templates:
		name = t["template_name"]
		label = f"Payment Terms Template '{name}'"
		rows = t.get("terms", [])
		if not frappe.db.exists("Payment Terms Template", name):
			if not dry_run:
				doc = frappe.get_doc(
					{
						"doctype": "Payment Terms Template",
						"template_name": name,
						"allocate_payment_based_on_payment_terms": t.get(
							"allocate_payment_based_on_payment_terms", 1
						),
					}
				)
				for r in rows:
					doc.append("terms", _pt_template_row(r))
				doc.insert(ignore_permissions=True)
			report["created"].append(f"{label} ({len(rows)} términos)")
			continue
		diffs = _pt_template_diff(name, rows)
		if not diffs:
			report["unchanged"].append(label)
		elif update_content:
			if not dry_run:
				doc = frappe.get_doc("Payment Terms Template", name)
				doc.set("terms", [])
				for r in rows:
					doc.append("terms", _pt_template_row(r))
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


def _seed_scope_items(items: list, report: dict, dry_run: bool, update_content: bool = False) -> None:
	fields = [
		"title",
		"sequence",
		"phase",
		"erpnext_item",
		"estimated_hours",
		"default_activity_type",
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
# ─────────────────────────────────────────────────────────────────────────────


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


def _existing_section_names() -> set:
	return set(frappe.get_all("Proposal Section", pluck="name"))


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
