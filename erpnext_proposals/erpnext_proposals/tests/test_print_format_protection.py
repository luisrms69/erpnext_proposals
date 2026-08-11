"""Candado de Print Formats históricos (utils/print_format_protection.py + doc_events).

Un Print Format referenciado por `proposal_effective_print_format` de una propuesta congelada queda
protegido contra modificación de presentación / `disabled` / rename / delete, preservando su
reimpresión. Un formato nunca usado permanece totalmente editable. Idempotente: re-guardar contenido
idéntico o metadata sin efecto en la presentación no bloquea.

Datos ficticios; nunca contenido de cliente.
"""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils.print_format_protection import (
	is_print_format_historical,
)

PF = "_Test PF Lock"
GROUP = "_PFLOCK-GRP"


def _purge():
	"""Deja el entorno limpio: quita referencias de las Quotations de prueba y borra sus formatos.

	Se quita primero `proposal_effective_print_format` para que los formatos dejen de ser históricos
	y puedan eliminarse (el candado bloquea el borrado de un formato histórico)."""
	for q in frappe.get_all("Quotation", filters={"proposal_group": GROUP}, pluck="name"):
		frappe.db.set_value("Quotation", q, "proposal_effective_print_format", None, update_modified=False)
		frappe.delete_doc("Quotation", q, force=True, ignore_permissions=True)
	for n in (PF, PF + " R"):
		if frappe.db.exists("Print Format", n):
			frappe.delete_doc("Print Format", n, force=True, ignore_permissions=True)
	frappe.db.commit()


def _mkpf(name):
	frappe.get_doc(
		{
			"doctype": "Print Format",
			"name": name,
			"doc_type": "Quotation",
			"standard": "No",
			"custom_format": 1,
			"print_format_type": "Jinja",
			"disabled": 0,
			"html": "<p>orig</p>",
		}
	).insert(ignore_permissions=True)


class TestPrintFormatProtection(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from erpnext_proposals.erpnext_proposals.tests.company import get_test_company

		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company on test site.")
		cls._fy = ensure_current_fiscal_year()
		cls._quotations = []

		from erpnext_proposals.erpnext_proposals.tests.company import get_test_item_group

		if not frappe.db.exists("Customer", "_PFLock Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_PFLock Customer",
					"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
					"territory": frappe.db.get_value("Territory", {}, "name"),
				}
			).insert(ignore_permissions=True)
		cls.customer = "_PFLock Customer"
		if not frappe.db.exists("Item", "_PFLOCK_ITEM"):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "_PFLOCK_ITEM",
					"item_name": "_PFLOCK_ITEM",
					"item_group": get_test_item_group(),
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"is_sales_item": 1,
				}
			).insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		cleanup_fiscal_year(getattr(cls, "_fy", None))
		super().tearDownClass()

	def setUp(self):
		_purge()

	def tearDown(self):
		_purge()

	def _make_historical(self):
		"""Crea una Quotation que deja PF como su `proposal_effective_print_format` (== histórico)."""
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"company": self.company,
				"currency": "MXN",
				"transaction_date": frappe.utils.today(),
				"proposal_group": GROUP,
				"items": [{"item_code": "_PFLOCK_ITEM", "qty": 1, "rate": 100}],
			}
		)
		doc.flags.ignore_mandatory = True
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		frappe.db.set_value(
			"Quotation", doc.name, "proposal_effective_print_format", PF, update_modified=False
		)
		self.__class__._quotations.append(doc.name)

	# ── Formato nunca usado: editable / rename / disable / delete ──
	def test_unused_format_is_editable(self):
		_mkpf(PF)
		self.assertFalse(is_print_format_historical(PF))
		pf = frappe.get_doc("Print Format", PF)
		pf.html = "<p>editado</p>"
		pf.save(ignore_permissions=True)  # no debe lanzar
		pf.reload()
		pf.disabled = 1
		pf.save(ignore_permissions=True)  # no debe lanzar
		frappe.rename_doc("Print Format", PF, PF + " R", force=True)  # no debe lanzar
		frappe.delete_doc("Print Format", PF + " R", ignore_permissions=True)  # no debe lanzar
		self.assertFalse(frappe.db.exists("Print Format", PF + " R"))

	# ── Formato histórico: bloquear modificación / disabled / rename / delete ──
	def test_historical_format_is_protected(self):
		_mkpf(PF)
		self._make_historical()
		self.assertTrue(is_print_format_historical(PF))

		pf = frappe.get_doc("Print Format", PF)
		pf.html = "<p>hack</p>"
		with self.assertRaises(frappe.ValidationError):
			pf.save(ignore_permissions=True)

		pf = frappe.get_doc("Print Format", PF)
		pf.disabled = 1
		with self.assertRaises(frappe.ValidationError):
			pf.save(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			frappe.rename_doc("Print Format", PF, PF + " X", force=True)

		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("Print Format", PF, ignore_permissions=True)

		# contenido intacto pese a los intentos
		self.assertEqual(frappe.db.get_value("Print Format", PF, "html"), "<p>orig</p>")
		self.assertEqual(frappe.db.get_value("Print Format", PF, "disabled"), 0)

	# ── Idempotencia: re-guardar igual o metadata sin efecto NO bloquea ──
	def test_historical_idempotent_save_not_blocked(self):
		_mkpf(PF)
		self._make_historical()
		self.assertTrue(is_print_format_historical(PF))
		# re-guardar sin cambios de presentación
		frappe.get_doc("Print Format", PF).save(ignore_permissions=True)  # no debe lanzar
		# cambio de metadata sin efecto en la presentación (module)
		pf = frappe.get_doc("Print Format", PF)
		pf.module = "ERPNext Proposals"
		pf.save(ignore_permissions=True)  # no debe lanzar
