import frappe
from frappe.model.document import Document


class ScopeItem(Document):
	def validate(self):
		self._no_commercial_fields_guard()

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
