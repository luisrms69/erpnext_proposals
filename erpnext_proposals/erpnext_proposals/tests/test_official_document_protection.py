"""Protección contra eliminación de los PDFs oficiales de la propuesta
(utils/official_document_protection.py + doc_events[File].on_trash + Custom Field marcador).

Un `File` marcado con `is_proposal_official_document=1` no puede borrarse por el flujo normal (ni
usuarios ordinarios ni System Manager); solo `Administrator`, y el propio flujo interno de reemplazo
(flag `INTERNAL_REPLACE_FLAG`). Los adjuntos NO marcados se borran normalmente. La protección depende
del marcador, no del `docstatus` de la Quotation (por eso se prueba en Borrador: Frappe nativo
permitiría borrar adjuntos de un documento en borrador, pero el marcador los sigue protegiendo — lo
mismo aplica tras cancelar).

Datos ficticios; nunca contenido de cliente.
"""

import unittest

import frappe
from frappe.utils.file_manager import save_file

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils.official_document_protection import (
	INTERNAL_REPLACE_FLAG,
	OFFICIAL_FLAG_FIELD,
)

GROUP = "_OFFDOC-GRP"
SM_USER = "_offdoc_sm@example.com"


class TestOfficialDocumentProtection(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_company

		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company on test site.")
		cls._fy = ensure_current_fiscal_year()

		from erpnext_proposals.erpnext_proposals.tests.company import get_test_item_group

		if not frappe.db.exists("Item", "_OFFDOC_ITEM"):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "_OFFDOC_ITEM",
					"item_name": "_OFFDOC_ITEM",
					"item_group": get_test_item_group(),
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"is_sales_item": 1,
				}
			).insert(ignore_permissions=True)

		# Usuario con rol System Manager (NO Administrator) para probar que tampoco puede borrar.
		if not frappe.db.exists("User", SM_USER):
			u = frappe.get_doc(
				{
					"doctype": "User",
					"email": SM_USER,
					"first_name": "OffDoc SM",
					"send_welcome_email": 0,
				}
			)
			u.insert(ignore_permissions=True)
			u.add_roles("System Manager")

		q = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": frappe.db.get_value("Customer", {}, "name"),
				"company": cls.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": GROUP,
				"items": [{"item_code": "_OFFDOC_ITEM", "qty": 1, "rate": 100}],
			}
		)
		q.flags.ignore_mandatory = True
		q.insert(ignore_permissions=True, ignore_mandatory=True)
		cls.quotation = q.name

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for f in frappe.get_all(
			"File",
			filters={"attached_to_doctype": "Quotation", "attached_to_name": cls.quotation},
			pluck="name",
		):
			frappe.delete_doc("File", f, force=True, ignore_permissions=True)
		if frappe.db.exists("Quotation", cls.quotation):
			frappe.delete_doc("Quotation", cls.quotation, force=True, ignore_permissions=True)
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		frappe.db.commit()
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def _mkfile(self, name, official):
		# Contenido ÚNICO por archivo: evita el dedup por content_hash de Frappe (que reutiliza el
		# archivo físico y rompe entre tests).
		f = save_file(
			fname=name,
			content=f"contenido {name} {frappe.generate_hash(length=8)}".encode(),
			dt="Quotation",
			dn=self.quotation,
			is_private=1,
		)
		if official:
			frappe.db.set_value("File", f.name, OFFICIAL_FLAG_FIELD, 1)
		return f.name

	def _del(self, name):
		frappe.delete_doc("File", name, ignore_permissions=True)

	# F / A — adjunto NO oficial: se borra normalmente
	def test_unmarked_file_is_deletable(self):
		fn = self._mkfile("adjunto_normal.txt", official=False)
		self._del(fn)  # no debe lanzar
		self.assertFalse(frappe.db.exists("File", fn))

	# B — oficial: usuario ordinario NO puede
	def test_official_blocked_for_ordinary_user(self):
		fn = self._mkfile("oficial_a.txt", official=True)
		frappe.set_user(SM_USER)  # cualquier no-Administrator (incluye System Manager)
		with self.assertRaises(frappe.ValidationError):
			self._del(fn)
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists("File", fn))

	# B — oficial: System Manager tampoco puede (mismo usuario SM verificado explícitamente)
	def test_official_blocked_for_system_manager(self):
		fn = self._mkfile("oficial_sm.txt", official=True)
		self.assertIn("System Manager", frappe.get_roles(SM_USER))
		frappe.set_user(SM_USER)
		with self.assertRaises(frappe.ValidationError):
			self._del(fn)
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists("File", fn))

	# B — oficial: Administrator SÍ puede
	def test_official_deletable_by_administrator(self):
		fn = self._mkfile("oficial_admin.txt", official=True)
		frappe.set_user("Administrator")
		self._del(fn)  # no debe lanzar
		self.assertFalse(frappe.db.exists("File", fn))

	# C — flujo interno de reemplazo: exento vía INTERNAL_REPLACE_FLAG
	def test_official_deletable_by_internal_replace_flag(self):
		fn = self._mkfile("oficial_interno.txt", official=True)
		frappe.set_user(SM_USER)  # aun siendo no-admin, el flag exime al flujo interno
		frappe.flags[INTERNAL_REPLACE_FLAG] = True
		try:
			self._del(fn)  # no debe lanzar
		finally:
			frappe.flags[INTERNAL_REPLACE_FLAG] = False
			frappe.set_user("Administrator")
		self.assertFalse(frappe.db.exists("File", fn))
