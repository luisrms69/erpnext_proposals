# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Helpers comunes de pruebas: masters deterministas (Company MXN + Item Group hoja).

Los tests que crean Quotations con ``currency="MXN"`` deben usar SIEMPRE la misma Company en MXN,
nunca "la primera Company" del site. `frappe.db.get_value("Company", {}, "name")` es NO determinista:
cuando en el site coexisten las Companies de prueba de ERPNext (creadas por el bootstrap de otras
apps — p. ej. al correr la suite de facturacion_mexico) puede devolver una Company USD/INR, y una
Quotation MXN contra una Company de otra moneda exige un tipo de cambio inexistente → falla.

Regla: en `setUpClass`/`_setup_master_data` usar `get_test_company()` en lugar de
`frappe.db.get_value("Company", {}, "name")`.

De forma análoga, los tests que crean `Item` deben usar `get_test_item_group()` en lugar de
`frappe.db.get_value("Item Group", {"is_group": 0}, "name")`. Un `bench new-site` + `install-app
erpnext` SIN Setup Wizard (como el site de CI) solo crea el grupo raíz `All Item Groups`
(`is_group=1`) y NINGÚN grupo hoja, por lo que el lookup directo devuelve ``None`` y el `Item`
falla con `MandatoryError: item_group`. El helper garantiza un grupo hoja (lo crea si falta),
igual que `get_test_company()` garantiza la Company.
"""

import frappe

TEST_COMPANY = "_Test Proposals Co"
TEST_COMPANY_ABBR = "_TPC"
TEST_COMPANY_CURRENCY = "MXN"

TEST_ITEM_GROUP = "_Test Proposals Item Group"
TEST_PRICE_LIST = "_Test Proposals Selling"


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


def get_test_item_group() -> str:
	"""Devuelve un Item Group hoja de pruebas, determinista e idempotente.

	- Si el site ya tiene algún Item Group hoja (`is_group=0`), devuelve ese (no ensucia).
	- Si no hay ninguno (site de CI sin Setup Wizard), crea `_Test Proposals Item Group`
	  colgando del primer grupo raíz disponible (`All Item Groups` u otro `is_group=1`),
	  creando incluso la raíz si tampoco existe.
	- Nunca depende de que el Setup Wizard haya sembrado `Services`/`Products`/etc.
	"""
	existing = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
	if existing:
		return existing
	parent = frappe.db.get_value("Item Group", {"is_group": 1}, "name")
	if not parent:
		parent = (
			frappe.get_doc({"doctype": "Item Group", "item_group_name": "All Item Groups", "is_group": 1})
			.insert(ignore_permissions=True)
			.name
		)
	if not frappe.db.exists("Item Group", TEST_ITEM_GROUP):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": TEST_ITEM_GROUP,
				"is_group": 0,
				"parent_item_group": parent,
			}
		).insert(ignore_permissions=True)
	return TEST_ITEM_GROUP


def get_test_cost_center(company: str | None = None) -> str:
	"""Devuelve un Cost Center hoja para la Company de pruebas, determinista e idempotente.

	El site fresco de CI crea el árbol de cuentas de la Company pero NO cost centers, por lo que
	`proposal_cost_center` (reqd=1) queda vacío y la Quotation falla con `MandatoryError`. El helper
	crea la raíz del árbol de cost centers de la Company (si falta) y un cost center hoja bajo ella.
	"""
	company = company or get_test_company()
	existing = frappe.db.get_value("Cost Center", {"is_group": 0, "company": company}, "name")
	if existing:
		return existing
	# ERPNext crea la raíz del árbol con flags.ignore_mandatory (no puede hacerse con un insert normal
	# porque `parent_cost_center` es obligatorio salvo en la raíz). Reutilizamos su propio método.
	frappe.get_doc("Company", company).create_default_cost_center()
	return frappe.db.get_value("Cost Center", {"is_group": 0, "company": company}, "name")


def get_test_price_list() -> str:
	"""Devuelve una Price List de venta en MXN, determinista e idempotente.

	El site fresco de CI no siembra ninguna Price List, por lo que `Quotation.selling_price_list`
	(y `price_list_currency`/`plc_conversion_rate` derivados) quedan vacíos y la Quotation falla al
	guardarse sin `ignore_mandatory`. El helper devuelve una Price List de venta existente o crea una
	en MXN (misma moneda que `get_test_company`, para conversion_rate = 1).
	"""
	existing = frappe.db.get_value("Price List", {"selling": 1}, "name")
	if existing:
		return existing
	if not frappe.db.exists("Price List", TEST_PRICE_LIST):
		frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": TEST_PRICE_LIST,
				"selling": 1,
				"currency": TEST_COMPANY_CURRENCY,
			}
		).insert(ignore_permissions=True)
	return TEST_PRICE_LIST
