import frappe
from frappe import _

_MANAGE_ROLES = frozenset(("System Manager", "Proposals Manager"))


def assert_can_manage_proposals() -> None:
	"""Raise PermissionError if the caller lacks proposal management access.

	Allowed: System Manager, Proposals Manager.
	Blocked: Proposals User, Sales User, and any other authenticated role.
	"""
	if not set(frappe.get_roles()).intersection(_MANAGE_ROLES):
		frappe.throw(
			_("Acceso denegado. Se requiere rol Proposals Manager o System Manager."),
			frappe.PermissionError,
		)
