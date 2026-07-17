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


def run(catalog_path: str | None = None, dry_run: bool = True, update_content: bool = False) -> dict:
	"""Punto de entrada. dry_run=True por defecto: no escribe, solo reporta el plan.

	catalog_path: ruta al JSON del catálogo (externo a la app). Si None, usa sample_catalog.json.
	update_content=True: además de crear lo inexistente, ACTUALIZA el contenido de los registros
	PROPIOS del catálogo cuando difieran. NUNCA toca las 10 Sections base ni secciones foráneas en uso.
	"""
	dry_run = _as_bool(dry_run)
	update_content = _as_bool(update_content) if update_content is not False else False
	data = _load_catalog(catalog_path)
	report: dict = {
		"created": [],
		"reused": [],
		"updated": [],
		"unchanged": [],
		"conflicts": [],
	}

	try:
		_seed_phases(data["phases"], report, dry_run)
		section_remap = _seed_sections(
			data["sections"], report, dry_run, update_content, set(data.get("versioned", []))
		)
		_seed_scope_items(data["scope_items"], report, dry_run)
		_seed_templates(data["templates"], section_remap, report, dry_run, update_content)
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
			continue

		current = frappe.db.get_value("Proposal Phase", code, ["phase_name", "sequence"], as_dict=True)
		diffs = _diff({"phase_name": p["phase_name"], "sequence": p["sequence"]}, current)
		if diffs:
			report["conflicts"].append(f"{label}: {diffs}")
		else:
			report["unchanged"].append(label)


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


def _seed_scope_items(items: list, report: dict, dry_run: bool) -> None:
	fields = [
		"title",
		"sequence",
		"phase",
		"visible_in_proposal",
		"is_internal_cost_task",
		"description",
		"deliverable",
	]
	for it in items:
		code = it["code"]
		label = f"Scope Item '{code}'"
		if not frappe.db.exists("Scope Item", code):
			if not dry_run:
				doc = {"doctype": "Scope Item", "code": code, "enabled": 1}
				for f in fields:
					doc[f] = it.get(f)
				frappe.get_doc(doc).insert(ignore_permissions=True)
			report["created"].append(label)
			continue

		current = frappe.db.get_value("Scope Item", code, fields, as_dict=True)
		expected = {f: it.get(f) for f in fields}
		diffs = _diff(expected, current)
		if diffs:
			report["conflicts"].append(f"{label}: {diffs}")
		else:
			report["unchanged"].append(label)


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
				for r in rows:
					doc.append("sections", _template_section_row(r))
				doc.insert(ignore_permissions=True)
			report["created"].append(f"{label} ({len(rows)} secciones)")
			continue

		# Existe: comparar filas. Si difiere y update_content → reconstruir las filas del template.
		diffs = _template_rows_diff(name, rows)
		if not diffs:
			report["unchanged"].append(label)
		elif update_content:
			if not dry_run:
				doc = frappe.get_doc("Proposal Template", name)
				if t.get("description"):
					doc.description = t["description"]
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
			)
			for r in expected_rows
		),
		key=lambda x: x[1],
	)
	if current == expected:
		return ""
	return f"{len(current)} filas actuales vs {len(expected)} del catálogo"


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
		f"  Conflictos:   {len(report['conflicts'])}",
		"-" * 70,
	]
	for bucket, title in (
		("created", "CREADOS"),
		("updated", "ACTUALIZADOS (contenido del catálogo)"),
		("conflicts", "CONFLICTOS (revisar — NO se modificaron)"),
	):
		if report[bucket]:
			lines.append(f"  {title}:")
			lines.extend(f"    · {x}" for x in report[bucket])
			lines.append("-" * 70)
	if dry_run and not report["conflicts"]:
		lines.append("  Dry-run OK. Para cargar: --kwargs \"{'dry_run': False}\"")
	if report["conflicts"]:
		lines.append("  ⚠️  Hay conflictos: revisa antes de cargar. El seeder no sobrescribe.")
	lines.append("=" * 70)
	print("\n".join(lines))
