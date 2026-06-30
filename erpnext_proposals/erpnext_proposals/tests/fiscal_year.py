# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Helper común de pruebas: aislamiento del Fiscal Year.

Los módulos que crean y someten Quotations requieren un Fiscal Year activo. Para que
cada módulo sea autosuficiente y aislado:

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ...resolver cls.company / masters...
        cls._created_fy = ensure_current_fiscal_year()
        ...crear/someter quotation...

    @classmethod
    def tearDownClass(cls):
        ...limpiar quotation...
        cleanup_fiscal_year(getattr(cls, "_created_fy", None))
        super().tearDownClass()

Regla: un módulo solo elimina el Fiscal Year que ÉL creó. Si ya existía uno, no lo
toca. Así ninguna prueba prepara silenciosamente el entorno de otras.
"""

import frappe


def ensure_current_fiscal_year():
	"""Garantiza un Fiscal Year que cubra la fecha de hoy.

	Devuelve el `name` del Fiscal Year si ESTA llamada lo creó, o `None` si ya
	existía uno. Pasar ese valor a `cleanup_fiscal_year` en el tearDownClass.
	"""
	today = frappe.utils.getdate()
	if frappe.get_all(
		"Fiscal Year",
		filters={"year_start_date": ["<=", today], "year_end_date": [">=", today]},
		limit=1,
	):
		return None

	year = today.year
	fy = frappe.get_doc(
		{
			"doctype": "Fiscal Year",
			"year": str(year),
			"year_start_date": f"{year}-01-01",
			"year_end_date": f"{year}-12-31",
		}
	).insert(ignore_permissions=True, ignore_if_duplicate=True)
	return fy.name


def cleanup_fiscal_year(created_name):
	"""Elimina el Fiscal Year solo si la prueba lo creó (`created_name` no es None)."""
	if created_name and frappe.db.exists("Fiscal Year", created_name):
		try:
			frappe.delete_doc("Fiscal Year", created_name, force=True, ignore_permissions=True)
		except Exception:
			pass
