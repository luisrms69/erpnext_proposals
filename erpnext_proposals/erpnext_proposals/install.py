"""
after_install hook for erpnext_proposals.

Syncs the app Desktop Icon so it appears without a manual sync-desktop-icons step.

IMPORTANT — no demo/commercial data on install:
This hook does NOT seed any Proposal Section or Proposal Template. Demo/placeholder content
must never be created on install or migrate (it would pollute production and every new install).

All commercial content (Proposal Templates, Sections, Items, Scope Items, Phases and Print
Formats) is delivered EXCLUSIVELY and EXPLICITLY through the private corporate catalog loader
(``catalog_loader.run`` with an external catalog path), never by ``after_install``/``migrate``.

Only technical structure ships with the app itself: DocTypes, Custom Fields, Property Setters,
public Print Formats (file-based, e.g. ``Propuesta Comercial`` / ``Rentabilidad Estimada``),
Roles/Workflow (fixtures) and the Desktop Icon synced here.
"""

import os

import frappe


def after_install():
	_sync_desktop_icons()


def _sync_desktop_icons():
	"""Import the app's Desktop Icon on install.

	Replicates the core ``sync-desktop-icons`` command for this app only, so a fresh
	install shows the workspace icon without requiring a separate manual command.
	"""
	from frappe.model.sync import import_file_by_path
	from frappe.modules.utils import get_app_level_directory_path

	directory_path = get_app_level_directory_path("desktop_icon", "erpnext_proposals")
	if not os.path.exists(directory_path):
		return

	for filename in os.listdir(directory_path):
		import_file_by_path(os.path.join(directory_path, filename), force=True, ignore_version=True)

	frappe.db.commit()  # nosemgrep — install hook: persist desktop icon
