import re

import frappe
from frappe import _
from frappe.model.document import Document

# Un offset válido es texto entero opcional: vacío/NULL = sin offset; '0' = inicio explícito; ±N días.
_OFFSET_RE = re.compile(r"^-?\d+$")


class ScopeItem(Document):
	def validate(self):
		self._no_commercial_fields_guard()
		self._validate_offset()
		self._validate_dependencies()

	def _validate_offset(self):
		"""planned_start_offset_days es Data nullable: vacío/NULL = sin offset explícito; '0' = inicio
		en Project.expected_start_date; entero ± = días después/antes. Se rechaza cualquier no-entero.
		La conversión a int se hace solo al calcular fechas (en project.py), nunca aquí."""
		raw = self.get("planned_start_offset_days")
		if raw is None or str(raw).strip() == "":
			return  # sin offset explícito — válido
		if not _OFFSET_RE.match(str(raw).strip()):
			frappe.throw(
				_(
					"El offset de inicio ('planned_start_offset_days') debe ser un entero como texto "
					"(vacío = sin offset, '0' = inicio del proyecto, ± = días). Valor inválido: {0}"
				).format(raw)
			)

	def _no_commercial_fields_guard(self):
		# Scope Item must never carry price, cost or rate — those live in ERPNext Item/Item Price
		forbidden = ("rate", "price", "cost", "amount", "margin")
		# Banderas booleanas de control que legítimamente contienen una de esas palabras
		# pero NO representan un valor comercial (no son precio/costo).
		allowed = {"is_internal_cost_task"}
		for field in self.meta.fields:
			if field.fieldname in allowed:
				continue
			if any(f in field.fieldname for f in forbidden):
				frappe.throw(
					f"Scope Item no puede tener campo comercial: {field.fieldname}. "
					"Los precios viven en ERPNext Item/Item Price."
				)

	def _validate_dependencies(self):
		"""depends_on_scope_items: sin auto-referencia, sin duplicados, sin ciclos.

		La existencia del Scope Item referenciado la garantiza el campo Link nativo. Aquí se
		bloquea que un Scope Item dependa de sí mismo, que repita una dependencia y que las
		cadenas de predecesores regresen a este mismo Scope Item (ciclo en el grafo del catálogo).
		"""
		self_code = self.name or self.code
		seen = set()
		for row in self.get("depends_on_scope_items") or []:
			dep = row.depends_on
			if not dep:
				continue
			if dep == self_code:
				frappe.throw(_("Un Scope Item no puede depender de sí mismo ({0}).").format(dep))
			if dep in seen:
				frappe.throw(_("Dependencia duplicada en el alcance: {0}.").format(dep))
			seen.add(dep)

		if seen and self_code:
			self._assert_no_dependency_cycle(self_code, seen)

	def _assert_no_dependency_cycle(self, self_code: str, direct_deps: set) -> None:
		"""DFS sobre el grafo de predecesores (persistido) partiendo de las dependencias directas
		de este documento. Si alguna cadena regresa a `self_code`, hay un ciclo."""
		visited: set = set()
		stack = list(direct_deps)
		while stack:
			node = stack.pop()
			if node == self_code:
				frappe.throw(
					_(
						"Dependencia cíclica detectada en {0}: la cadena de predecesores regresa a "
						"este Scope Item."
					).format(self_code)
				)
			if node in visited:
				continue
			visited.add(node)
			preds = frappe.get_all(
				"Scope Item Dependency",
				filters={
					"parenttype": "Scope Item",
					"parentfield": "depends_on_scope_items",
					"parent": node,
				},
				pluck="depends_on",
			)
			stack.extend(p for p in preds if p and p not in visited)
