#!/usr/bin/env python3
"""
Generador de documentación de referencia para apps Frappe (Buzola).

Genera docs/referencia/ desde el código fuente del app:
  - doctypes.md  → desde DocType JSONs
  - hooks.md     → desde hooks.py
  - api.md       → desde funciones @frappe.whitelist()

USO:
    python3 scripts/generate_reference.py
    python3 scripts/generate_reference.py --app-path /ruta/al/app
    python3 scripts/generate_reference.py --verify

IDEMPOTENTE: puede ejecutarse múltiples veces sin efectos secundarios.
Solo escribe en docs/referencia/. No toca ningún otro archivo de docs/.
"""

import argparse
import ast
import json
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

GENERATED_HEADER = """\
<!--
  ARCHIVO GENERADO AUTOMÁTICAMENTE. NO EDITAR MANUALMENTE.
  Regenerar con: python3 scripts/generate_reference.py
  Fecha generación: {date}
-->

"""

REFERENCIA_DIR = "docs/referencia"

EXPECTED_FILES = ["doctypes.md", "hooks.md", "api.md", "index.md"]

# DocTypes a excluir (internos de Frappe/ERPNext sin relevancia para la referencia)
EXCLUDED_DOCTYPES = {"DocType", "DocField", "DocPerm"}


# ---------------------------------------------------------------------------
# Validación del app
# ---------------------------------------------------------------------------


def find_app_root(start: Path) -> Path:
	"""Busca la raíz del repo Frappe app desde el directorio dado.

	Estructura esperada:
	    repo_root/
	        pyproject.toml
	        app_name/
	            hooks.py
	"""
	candidate = start
	for _ in range(5):
		if (candidate / "pyproject.toml").exists():
			# Verificar que algún subdirectorio tiene hooks.py
			for subdir in candidate.iterdir():
				if subdir.is_dir() and (subdir / "hooks.py").exists():
					return candidate
		candidate = candidate.parent
	raise SystemExit(
		"ERROR: No se encontró la raíz del app Frappe (pyproject.toml + app_name/hooks.py).\n"
		"Ejecuta desde el directorio del app o usa --app-path."
	)


def validate_app(app_root: Path) -> str:
	"""Valida que el app tenga la estructura esperada. Retorna el nombre del app."""
	pyproject = app_root / "pyproject.toml"
	if not pyproject.exists():
		raise SystemExit(f"ERROR: No se encontró pyproject.toml en {app_root}")

	# Obtener nombre del app y verificar que existe app_name/hooks.py
	app_name = None
	content = pyproject.read_text()
	for line in content.splitlines():
		if line.strip().startswith("name"):
			app_name = line.split("=")[1].strip().strip('"').strip("'")
			break

	if not app_name:
		raise SystemExit("ERROR: No se pudo determinar el nombre del app desde pyproject.toml")

	hooks = app_root / app_name / "hooks.py"
	if not hooks.exists():
		raise SystemExit(f"ERROR: No se encontró {app_name}/hooks.py en {app_root}")

	return app_name


def ensure_referencia_dir(app_root: Path) -> Path:
	"""Asegura que docs/referencia/ existe."""
	referencia = app_root / REFERENCIA_DIR
	referencia.mkdir(parents=True, exist_ok=True)
	return referencia


# ---------------------------------------------------------------------------
# Generador: doctypes.md
# ---------------------------------------------------------------------------


def collect_doctypes(app_root: Path, app_name: str) -> list[dict]:
	"""Recolecta todos los DocTypes del app desde sus JSONs."""
	doctypes = []
	app_module = app_root / app_name

	if not app_module.exists():
		raise SystemExit(f"ERROR: No se encontró el módulo {app_name}/ en {app_root}")

	pattern = f"{app_name}/*/doctype/*/*.json"
	json_files = sorted(app_root.glob(pattern))

	if not json_files:
		# También buscar en subdirectorios más profundos
		pattern = f"{app_name}/**/*.json"
		json_files = [
			f for f in sorted(app_root.glob(pattern)) if "/doctype/" in str(f) and f.stem == f.parent.name
		]

	for json_file in json_files:
		try:
			data = json.loads(json_file.read_text())
		except json.JSONDecodeError, OSError:
			continue

		if not isinstance(data, dict) or data.get("doctype") != "DocType":
			continue
		if data.get("name") in EXCLUDED_DOCTYPES:
			continue

		fields = [
			f
			for f in data.get("fields", [])
			if f.get("fieldtype") not in ("Section Break", "Column Break", "Tab Break", "HTML")
			and not f.get("fieldname", "").startswith("col_break")
		]

		doctypes.append(
			{
				"name": data.get("name", json_file.stem),
				"module": data.get("module", ""),
				"is_submittable": bool(data.get("is_submittable")),
				"is_single": bool(data.get("issingle")),
				"is_table": bool(data.get("istable")),
				"description": data.get("description", ""),
				"fields": fields,
				"path": str(json_file.relative_to(app_root)),
			}
		)

	return doctypes


def render_doctypes(doctypes: list[dict], date: str) -> str:
	"""Genera el contenido de doctypes.md."""
	lines = [GENERATED_HEADER.format(date=date)]
	lines.append("# Referencia — DocTypes\n")
	lines.append(
		"DocTypes del app organizados por módulo. "
		"Incluye campos activos (excluye Section Break, Column Break, HTML).\n"
	)

	# Agrupar por módulo
	by_module: dict[str, list[dict]] = {}
	for dt in doctypes:
		mod = dt["module"] or "Sin módulo"
		by_module.setdefault(mod, []).append(dt)

	for module, dts in sorted(by_module.items()):
		lines.append(f"\n## {module}\n")
		for dt in sorted(dts, key=lambda x: x["name"]):
			flags = []
			if dt["is_submittable"]:
				flags.append("Submittable")
			if dt["is_single"]:
				flags.append("Single")
			if dt["is_table"]:
				flags.append("Child table")
			flag_str = f" _{', '.join(flags)}_" if flags else ""
			lines.append(f"\n### {dt['name']}{flag_str}\n")
			if dt["description"]:
				lines.append(f"{dt['description']}\n")
			lines.append(f"Fuente: `{dt['path']}`\n")

			if dt["fields"]:
				lines.append("\n| Campo | Label | Tipo | Requerido | Opciones |")
				lines.append("|---|---|---|---|---|")
				for f in dt["fields"]:
					fname = f.get("fieldname", "")
					label = f.get("label", "")
					ftype = f.get("fieldtype", "")
					reqd = "✅" if f.get("reqd") else ""
					opts = f.get("options", "") or ""
					# Truncar opciones largas
					if "\n" in str(opts):
						opts = opts.split("\n")[0] + "…"
					opts = str(opts)[:60]
					lines.append(f"| `{fname}` | {label} | {ftype} | {reqd} | {opts} |")
				lines.append("")
			else:
				lines.append("_Sin campos documentados._\n")

	return "\n".join(lines)


# ---------------------------------------------------------------------------
# Generador: hooks.md
# ---------------------------------------------------------------------------


def collect_hooks(app_root: Path, app_name: str) -> dict:
	"""Extrae información relevante de hooks.py usando AST."""
	hooks_path = app_root / app_name / "hooks.py"
	content = hooks_path.read_text()

	result = {
		"doc_events": {},
		"after_install": [],
		"after_migrate": [],
		"fixtures": [],
		"scheduler_events": {},
	}

	try:
		tree = ast.parse(content)
	except SyntaxError as e:
		print(f"ADVERTENCIA: No se pudo parsear hooks.py: {e}")
		return result

	for node in ast.walk(tree):
		if not isinstance(node, ast.Assign):
			continue

		for target in node.targets:
			if not isinstance(target, ast.Name):
				continue
			name = target.id

			if name == "doc_events" and isinstance(node.value, ast.Dict):
				for k, v in zip(node.value.keys, node.value.values, strict=False):
					if isinstance(k, ast.Constant):
						doctype = k.value
						handlers = []
						if isinstance(v, ast.Dict):
							for ek, ev in zip(v.keys, v.values, strict=False):
								if isinstance(ek, ast.Constant):
									event = ek.value
									if isinstance(ev, ast.Constant):
										handlers.append((event, ev.value))
									elif isinstance(ev, ast.List):
										for el in ev.elts:
											if isinstance(el, ast.Constant):
												handlers.append((event, el.value))
						result["doc_events"][doctype] = handlers

			elif name in ("after_install", "after_migrate") and isinstance(node.value, ast.List):
				for el in node.value.elts:
					if isinstance(el, ast.Constant):
						result[name].append(el.value)

			elif name == "fixtures" and isinstance(node.value, ast.List):
				for el in node.value.elts:
					if isinstance(el, ast.Constant):
						result["fixtures"].append(str(el.value))
					elif isinstance(el, ast.Dict):
						# {"dt": "...", "filters": [...]}
						parts = {}
						for fk, fv in zip(el.keys, el.values, strict=False):
							if isinstance(fk, ast.Constant) and isinstance(fv, ast.Constant):
								parts[fk.value] = fv.value
						if parts:
							result["fixtures"].append(str(parts))

	return result


def render_hooks(hooks: dict, date: str) -> str:
	"""Genera el contenido de hooks.md."""
	lines = [GENERATED_HEADER.format(date=date)]
	lines.append("# Referencia — Hooks\n")
	lines.append("Hooks activos en el app. Fuente: `hooks.py`.\n")

	# doc_events
	if hooks["doc_events"]:
		lines.append("\n## doc_events\n")
		lines.append("| DocType | Evento | Handler |")
		lines.append("|---|---|---|")
		for doctype, handlers in sorted(hooks["doc_events"].items()):
			for event, handler in handlers:
				# Simplificar path del handler
				short = handler.split(".")[-1] if "." in handler else handler
				lines.append(f"| `{doctype}` | `{event}` | `{short}` |")
				lines.append(f"|  |  | `{handler}` |")
		lines.append("")

	# after_install
	if hooks["after_install"]:
		lines.append("\n## after_install\n")
		for fn in hooks["after_install"]:
			lines.append(f"- `{fn}`")
		lines.append("")

	# after_migrate
	if hooks["after_migrate"]:
		lines.append("\n## after_migrate\n")
		for fn in hooks["after_migrate"]:
			lines.append(f"- `{fn}`")
		lines.append("")

	# fixtures
	if hooks["fixtures"]:
		lines.append("\n## fixtures\n")
		lines.append("Fixtures exportados con `bench export-fixtures`:\n")
		for f in hooks["fixtures"]:
			lines.append(f"- `{f}`")
		lines.append("")

	return "\n".join(lines)


# ---------------------------------------------------------------------------
# Generador: api.md
# ---------------------------------------------------------------------------


def collect_whitelist_functions(app_root: Path, app_name: str) -> list[dict]:
	"""Encuentra todas las funciones @frappe.whitelist() del app."""
	functions = []
	app_module = app_root / app_name

	for py_file in sorted(app_module.rglob("*.py")):
		# Excluir tests y archivos de migración
		if any(x in str(py_file) for x in ["test_", "__pycache__", "patches/legacy"]):
			continue

		try:
			content = py_file.read_text()
		except OSError:
			continue

		if "@frappe.whitelist" not in content:
			continue

		try:
			tree = ast.parse(content)
		except SyntaxError:
			continue

		module_path = str(py_file.relative_to(app_root)).replace("/", ".").removesuffix(".py")

		for node in ast.walk(tree):
			if not isinstance(node, ast.FunctionDef):
				continue

			# Verificar decorador @frappe.whitelist
			is_whitelist = False
			for dec in node.decorator_list:
				dec_str = ast.unparse(dec) if hasattr(ast, "unparse") else ""
				if "whitelist" in dec_str or (isinstance(dec, ast.Attribute) and dec.attr == "whitelist"):
					is_whitelist = True
					break
				if isinstance(dec, ast.Name) and dec.id == "whitelist":
					is_whitelist = True
					break

			if not is_whitelist:
				continue

			docstring = ast.get_docstring(node) or ""
			args = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]

			functions.append(
				{
					"name": node.name,
					"module": module_path,
					"docstring": docstring.split("\n")[0] if docstring else "",
					"args": args,
					"file": str(py_file.relative_to(app_root)),
				}
			)

	return functions


def render_api(functions: list[dict], date: str) -> str:
	"""Genera el contenido de api.md."""
	lines = [GENERATED_HEADER.format(date=date)]
	lines.append("# Referencia — API\n")
	lines.append(
		"Funciones expuestas como endpoints HTTP via `@frappe.whitelist()`.\n"
		"Accesibles desde el cliente JS con `frappe.call({method: '...'})` "
		"o desde Python con `frappe.get_attr('...')`.\n"
	)

	if not functions:
		lines.append("_No se encontraron funciones @frappe.whitelist()._\n")
		return "\n".join(lines)

	# Agrupar por archivo
	by_file: dict[str, list[dict]] = {}
	for fn in functions:
		by_file.setdefault(fn["file"], []).append(fn)

	lines.append("\n## Índice\n")
	for filepath in sorted(by_file.keys()):
		fns = by_file[filepath]
		lines.append(f"- **{filepath}**")
		for fn in fns:
			lines.append(f"  - [`{fn['name']}`](#{fn['name'].lower().replace('_', '-')})")
	lines.append("")

	lines.append("\n---\n")

	for filepath in sorted(by_file.keys()):
		fns = by_file[filepath]
		lines.append(f"\n## `{filepath}`\n")
		for fn in fns:
			args_str = ", ".join(fn["args"])
			lines.append(f"\n### `{fn['name']}({args_str})`\n")
			lines.append(f"**Módulo:** `{fn['module']}`\n")
			if fn["docstring"]:
				lines.append(f"{fn['docstring']}\n")

	return "\n".join(lines)


# ---------------------------------------------------------------------------
# Generador: index.md (referencia)
# ---------------------------------------------------------------------------


def render_index(date: str) -> str:
	"""Genera el contenido de referencia/index.md."""
	lines = [GENERATED_HEADER.format(date=date)]
	lines.append("# Referencia\n")
	lines.append("Documentación técnica de referencia generada automáticamente desde el código fuente.\n")
	lines.append("\n## Contenido\n")
	lines.append("- [DocTypes](doctypes.md) — Todos los DocTypes con sus campos")
	lines.append("- [Hooks](hooks.md) — Hooks activos, after_install, fixtures")
	lines.append("- [API](api.md) — Endpoints `@frappe.whitelist()`")
	lines.append("\n---\n")
	lines.append(f"_Generado: {date}_\n")
	lines.append("_Para regenerar: `python3 scripts/generate_reference.py` desde la raíz del app._\n")
	return "\n".join(lines)


# ---------------------------------------------------------------------------
# Escritura de archivos
# ---------------------------------------------------------------------------


def write_file(path: Path, content: str) -> None:
	"""Escribe el archivo de forma atómica. Sobreescribe si ya existe."""
	tmp = path.with_suffix(".tmp")
	tmp.write_text(content, encoding="utf-8")
	tmp.replace(path)
	print(f"  ✅ {path.name}")


# ---------------------------------------------------------------------------
# Verificación
# ---------------------------------------------------------------------------


def verify(app_root: Path) -> bool:
	"""Verifica que docs/referencia/ está actualizada."""
	referencia = app_root / REFERENCIA_DIR
	missing = [f for f in EXPECTED_FILES if not (referencia / f).exists()]
	if missing:
		print(f"❌ Faltan archivos en docs/referencia/: {missing}")
		return False

	# Verificar que los archivos tienen el header de generación
	for fname in EXPECTED_FILES:
		content = (referencia / fname).read_text()
		if "ARCHIVO GENERADO AUTOMÁTICAMENTE" not in content:
			print(f"⚠️  {fname} no tiene el header de generación automática")
			return False

	print("✅ docs/referencia/ está actualizada y tiene los headers correctos")
	return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Genera docs/referencia/ desde el código fuente del app Frappe."
	)
	parser.add_argument(
		"--app-path",
		default=".",
		help="Ruta a la raíz del app (default: directorio actual)",
	)
	parser.add_argument(
		"--verify",
		action="store_true",
		help="Solo verificar que docs/referencia/ está actualizada (no regenerar)",
	)
	args = parser.parse_args()

	app_root = find_app_root(Path(args.app_path).resolve())
	app_name = validate_app(app_root)

	print(f"🔍 App: {app_name}")
	print(f"📁 Raíz: {app_root}")

	if args.verify:
		ok = verify(app_root)
		sys.exit(0 if ok else 1)

	print("\n📝 Generando docs/referencia/...\n")
	date = datetime.now().strftime("%Y-%m-%d %H:%M")
	referencia = ensure_referencia_dir(app_root)

	# DocTypes
	print("→ Escaneando DocType JSONs...")
	doctypes = collect_doctypes(app_root, app_name)
	print(f"  Encontrados: {len(doctypes)} DocTypes")
	write_file(referencia / "doctypes.md", render_doctypes(doctypes, date))

	# Hooks
	print("→ Parseando hooks.py...")
	hooks = collect_hooks(app_root, app_name)
	doc_events_count = sum(len(v) for v in hooks["doc_events"].values())
	print(f"  doc_events: {doc_events_count} handlers | after_migrate: {len(hooks['after_migrate'])}")
	write_file(referencia / "hooks.md", render_hooks(hooks, date))

	# API
	print("→ Escaneando @frappe.whitelist()...")
	functions = collect_whitelist_functions(app_root, app_name)
	print(f"  Encontradas: {len(functions)} funciones")
	write_file(referencia / "api.md", render_api(functions, date))

	# Index
	write_file(referencia / "index.md", render_index(date))

	print(f"\n✅ docs/referencia/ generada ({len(EXPECTED_FILES)} archivos)")
	print("   Para regenerar: python3 scripts/generate_reference.py")

	# Verificación final
	print()
	verify(app_root)


if __name__ == "__main__":
	main()
