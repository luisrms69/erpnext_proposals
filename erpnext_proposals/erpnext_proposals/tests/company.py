# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Helper común de pruebas: Company determinista en MXN.

Los tests que crean Quotations con ``currency="MXN"`` deben usar SIEMPRE la misma Company en MXN,
nunca "la primera Company" del site. `frappe.db.get_value("Company", {}, "name")` es NO determinista:
cuando en el site coexisten las Companies de prueba de ERPNext (creadas por el bootstrap de otras
apps — p. ej. al correr la suite de facturacion_mexico) puede devolver una Company USD/INR, y una
Quotation MXN contra una Company de otra moneda exige un tipo de cambio inexistente → falla.

Regla: en `setUpClass`/`_setup_master_data` usar `get_test_company()` en lugar de
`frappe.db.get_value("Company", {}, "name")`.
"""

import frappe

TEST_COMPANY = "_Test Proposals Co"
TEST_COMPANY_ABBR = "_TPC"
TEST_COMPANY_CURRENCY = "MXN"


def get_test_company() -> str:
	"""Devuelve la Company de pruebas de erpnext_proposals en MXN.

	Determinista e idempotente:
	- Si `_Test Proposals Co` existe, la devuelve (es MXN por construcción).
	- Si no existe, la crea mínima en MXN.
	- Nunca selecciona "la primera Company" del site ni depende de Global Defaults.
	- No modifica ni elimina Companies creadas por otras suites (ERPNext, etc.).
	"""
	if not frappe.db.exists("Company", TEST_COMPANY):
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": TEST_COMPANY,
				"abbr": TEST_COMPANY_ABBR,
				"default_currency": TEST_COMPANY_CURRENCY,
				"country": "Mexico",
			}
		).insert(ignore_permissions=True)
	return TEST_COMPANY
