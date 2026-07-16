"""Helper común de pruebas: catálogo Proposal Phase.

`phase` es un Link a Proposal Phase, por lo que los tests deben usar registros reales.
El orden alfabético del `code` (DISC, GOLIVE, IMPL) difiere **a propósito** del orden por
`sequence` (DISC=10, IMPL=20, GOLIVE=30), para poder validar el ordenamiento por sequence.

Uso (mismo patrón que fiscal_year.py — cada módulo crea/limpia lo suyo):

    cls._created_phases = ensure_test_phases()
    ...
    cleanup_test_phases(cls._created_phases)
"""

import frappe

# (phase_code, phase_name, sequence)
TEST_PHASES = (
	("DISC", "Descubrimiento", 10),
	("IMPL", "Implementación", 20),
	("GOLIVE", "Puesta en marcha", 30),
)


def ensure_test_phases():
	"""Crea las Proposal Phase de prueba que falten. Devuelve la lista de codes creados."""
	created = []
	for code, name, seq in TEST_PHASES:
		if not frappe.db.exists("Proposal Phase", code):
			frappe.get_doc(
				{
					"doctype": "Proposal Phase",
					"phase_code": code,
					"phase_name": name,
					"sequence": seq,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
			created.append(code)
	return created


def cleanup_test_phases(created):
	"""Elimina solo las Proposal Phase que esta prueba creó."""
	for code in created or []:
		if frappe.db.exists("Proposal Phase", code):
			try:
				frappe.delete_doc("Proposal Phase", code, force=True, ignore_permissions=True)
			except Exception:
				pass
