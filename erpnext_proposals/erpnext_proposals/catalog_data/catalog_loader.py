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
LOADER_CAPS_VERSION = 4


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
	}

	try:
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
		# Print Formats antes que Templates: Proposal Template.print_format es un Link que
		# requiere que el Print Format exista al guardar el template.
		_seed_print_formats(data.get("print_formats", []), catalog_dir, report, dry_run, update_content)
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


def _seed_items(items: list, report: dict, dry_run: bool, update_content: bool = False) -> None:
	"""Crea/actualiza idempotentemente ERPNext Items (capacidad genérica). Identidad: item_code.
	Los datos concretos (nombres, grupos, descripciones) viven en el catálogo externo, no en el app.
	Solo se comparan/actualizan los campos que el catálogo provee (no se fuerzan vacíos)."""
	fields = ["item_name", "item_group", "stock_uom", "is_stock_item", "is_sales_item", "description"]
	for it in items:
		code = it["item_code"]
		label = f"Item '{code}'"
		provided = {f: it.get(f) for f in fields if it.get(f) is not None}
		if not frappe.db.exists("Item", code):
			if not dry_run:
				doc = {"doctype": "Item", "item_code": code}
				doc.update(provided)
				frappe.get_doc(doc).insert(ignore_permissions=True)
			report["created"].append(label)
			continue

		current = frappe.db.get_value("Item", code, list(provided.keys()), as_dict=True) if provided else {}
		diffs = _diff(provided, current)
		if not diffs:
			report["unchanged"].append(label)
		elif update_content:
			if not dry_run:
				doc = frappe.get_doc("Item", code)
				for f, v in provided.items():
					doc.set(f, v)
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


def _seed_print_formats(
	pfs: list, catalog_dir: str, report: dict, dry_run: bool, update_content: bool = False
) -> None:
	"""Crea/actualiza idempotentemente Print Formats como assets administrados por el catálogo
	(capacidad genérica). Identidad: name.

	- El HTML (Jinja) y el CSS viven en archivos externos referenciados por `html_file`/`css_file`
	  (rutas relativas al JSON del catálogo); se leen y componen aquí. El `html` final autocontiene
	  el `<style>` (robusto en wkhtmltopdf) y el `css` field se conserva por compatibilidad.
	- Nunca toca los Print Formats PROTEGIDOS (assets del repo público); si el catálogo intenta
	  administrar uno, se reporta como conflicto y se omite.
	- Solo administra los campos provistos por el spec; el resto usa el default del DocType.
	"""
	fields = [
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
	]
	for pf in pfs:
		name = pf["name"]
		label = f"Print Format '{name}'"
		if name in PROTECTED_PRINT_FORMATS:
			report["conflicts"].append(f"{label}: PROTEGIDO — el loader nunca lo crea ni modifica")
			continue

		spec = _resolve_print_format_spec(pf, catalog_dir)
		provided = {f: spec.get(f) for f in fields if spec.get(f) is not None}
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
		elif update_content:
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
		# Campos editoriales opcionales del alcance (Text Editor). Administrados igual que
		# description/deliverable: clave presente fija el valor, null explícito lo limpia, ausente no toca.
		"service_objective",
		"methodology",
		"expected_result",
		"scope_limit",
		"exclusions",
		"acceptance_criteria",
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
		keys = list(provided.keys()) + list(cleared)
		if not frappe.db.exists("Scope Item", code):
			if not dry_run:
				doc = {"doctype": "Scope Item", "code": code, "enabled": 1}
				doc.update(provided)
				for f in cleared:
					doc[f] = None
				frappe.get_doc(doc).insert(ignore_permissions=True)
			report["created"].append(label)
			continue

		current = frappe.db.get_value("Scope Item", code, keys, as_dict=True) if keys else {}
		diffs = _diff_managed(provided, cleared, current)
		if not diffs:
			report["unchanged"].append(label)
		elif update_content:
			if not dry_run:
				doc = frappe.get_doc("Scope Item", code)
				for f, v in provided.items():
					doc.set(f, v)
				for f in cleared:
					doc.set(f, None)
				doc.save(ignore_permissions=True)
			report["updated"].append(f"{label}: {diffs}")
		else:
			report["conflicts"].append(f"{label}: {diffs}")


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
		if not diffs:
			report["unchanged"].append(label)
		elif update_content:
			if not dry_run:
				doc = frappe.get_doc("Proposal Template", name)
				if t.get("description"):
					doc.description = t["description"]
				if t.get("print_format"):
					doc.print_format = t["print_format"]
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
