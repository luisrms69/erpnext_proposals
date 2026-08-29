"""Candado de Print Formats históricos (utils/print_format_protection.py + doc_events).

Un Print Format referenciado por `proposal_effective_print_format` de una propuesta congelada queda
protegido contra modificación de CONTENIDO/presentación (HTML/CSS/…) / rename / delete. `disabled` NO
está protegido (modelo 2026-08-12, ADR-0011): un formato histórico SÍ puede pasar a `disabled=1` al ser
sustituido. Un formato nunca usado permanece totalmente editable. Idempotente: re-guardar contenido
idéntico o metadata sin efecto en la presentación no bloquea.

Datos ficticios; nunca contenido de cliente.
"""

import unittest
from unittest.mock import patch

import frappe

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils import print_format_protection as pfp
from erpnext_proposals.erpnext_proposals.utils.print_format_protection import (
	is_print_format_historical,
)

PF = "_Test PF Lock"
GROUP = "_PFLOCK-GRP"


# PDF mínimo VÁLIDO (pypdf lo parsea al adjuntar el File). El comentario `% {tag}` lo hace de contenido
# ÚNICO por archivo para evitar la deduplicación de Frappe por content_hash.
def _pdf(tag: bytes) -> bytes:
	return (
		b"%PDF-1.4\n% " + tag + b"\n"
		b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
		b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
		b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
		b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
		b"0000000058 00000 n \n0000000115 00000 n \n"
		b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF\n"
	)


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
		return doc.name

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

	# ── Formato histórico: bloquear modificación de CONTENIDO / rename / delete ──
	def test_historical_format_content_is_protected(self):
		_mkpf(PF)
		self._make_historical()
		self.assertTrue(is_print_format_historical(PF))

		# HTML protegido
		pf = frappe.get_doc("Print Format", PF)
		pf.html = "<p>hack</p>"
		with self.assertRaises(frappe.ValidationError):
			pf.save(ignore_permissions=True)

		# CSS protegido
		pf = frappe.get_doc("Print Format", PF)
		pf.css = ".x{color:red}"
		with self.assertRaises(frappe.ValidationError):
			pf.save(ignore_permissions=True)

		# rename protegido
		with self.assertRaises(frappe.ValidationError):
			frappe.rename_doc("Print Format", PF, PF + " X", force=True)

		# delete protegido
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("Print Format", PF, ignore_permissions=True)

		# contenido intacto pese a los intentos
		self.assertEqual(frappe.db.get_value("Print Format", PF, "html"), "<p>orig</p>")

	# ── Formato histórico: `disabled` SÍ puede cambiar 0 → 1 (modelo 2026-08-12; ADR-0011 actualizado) ──
	def test_historical_format_can_be_disabled(self):
		_mkpf(PF)
		self._make_historical()
		self.assertTrue(is_print_format_historical(PF))
		self.assertEqual(frappe.db.get_value("Print Format", PF, "disabled"), 0)

		pf = frappe.get_doc("Print Format", PF)
		pf.disabled = 1
		pf.save(ignore_permissions=True)  # NO debe lanzar: `disabled` no es representación histórica

		self.assertEqual(frappe.db.get_value("Print Format", PF, "disabled"), 1)
		# el contenido sigue intacto y el formato sigue siendo histórico (referencia/auditoría)
		self.assertEqual(frappe.db.get_value("Print Format", PF, "html"), "<p>orig</p>")
		self.assertTrue(is_print_format_historical(PF))

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

	# ── Congelada conserva `proposal_effective_print_format` como referencia aunque el formato quede
	#    disabled (auditoría, no reimpresión) ──
	def test_frozen_keeps_effective_ref_when_disabled(self):
		_mkpf(PF)
		name = self._make_historical()
		pf = frappe.get_doc("Print Format", PF)
		pf.disabled = 1
		pf.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Print Format", PF, "disabled"), 1)
		# la referencia de auditoría persiste intacta
		self.assertEqual(frappe.db.get_value("Quotation", name, "proposal_effective_print_format"), PF)

	# ── Consulta normal de una congelada usa los PDFs oficiales adjuntos (no requiere re-render) ──
	def test_normal_consult_uses_official_pdfs(self):
		from frappe.utils.file_manager import save_file

		from erpnext_proposals.erpnext_proposals.utils.quotation import get_proposal_documents_status

		_mkpf(PF)
		name = self._make_historical()  # proposal_effective_print_format = PF
		# Sin oficiales adjuntos: la comprobación real reporta ausencia (el JS ofrecería regenerar).
		st0 = get_proposal_documents_status(name)
		self.assertFalse(st0["commercial"])
		self.assertFalse(st0["rentabilidad"])
		# Adjuntar los PDFs oficiales PRIVADOS con los prefijos que produce el freeze.
		save_file(f"{PF} - {name}.pdf", _pdf(b"commercial"), "Quotation", name, is_private=1)
		save_file(
			f"Rentabilidad Estimada - {name}.pdf", _pdf(b"rentabilidad"), "Quotation", name, is_private=1
		)
		frappe.db.commit()
		# Ahora la comprobación real confirma presencia → el JS oculta las acciones de RE-generar y sirve
		# solo descarga (consulta normal sin re-render de la congelada).
		st1 = get_proposal_documents_status(name)
		self.assertTrue(st1["commercial"])
		self.assertTrue(st1["rentabilidad"])
		self.assertTrue(st1["official_present"])


class _FakePF:
	"""Doc mínimo para ejercitar el guard sin BD (el campo aún no está migrado en meta)."""

	def __init__(self, name: str, changed: set):
		self.name = name
		self._changed = set(changed)

	def get(self, key, default=None):
		return default  # `__islocal` ausente → falsy

	def is_new(self):
		return False

	def has_value_changed(self, field):
		return field in self._changed


class TestRendererProfileHistoricalLock(unittest.TestCase):
	"""ADR-0015 sobre ADR-0011: el renderer profile de un PF histórico es inmutable (mismo candado).

	Unitario sobre el guard real y `_PRESENTATION_FIELDS` — no requiere el Custom Field migrado, así que
	puede correr ANTES del migrate (gatea la autorización del migrate)."""

	def test_renderer_profile_is_a_protected_presentation_field(self):
		self.assertIn("proposal_renderer_profile", pfp._PRESENTATION_FIELDS)

	def test_historical_pf_cannot_change_renderer_profile(self):
		doc = _FakePF("_Test PF", {"proposal_renderer_profile"})
		with patch.object(pfp, "is_print_format_historical", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				pfp.protect_historical_print_format_on_save(doc)

	def test_non_historical_pf_can_change_renderer_profile(self):
		doc = _FakePF("_Test PF", {"proposal_renderer_profile"})
		with patch.object(pfp, "is_print_format_historical", return_value=False):
			pfp.protect_historical_print_format_on_save(doc)  # no debe lanzar

	def test_historical_pf_unrelated_change_not_blocked(self):
		"""Sin cambio en campos protegidos (idempotencia) no bloquea, aunque sea histórico."""
		doc = _FakePF("_Test PF", set())
		with patch.object(pfp, "is_print_format_historical", return_value=True):
			pfp.protect_historical_print_format_on_save(doc)  # no debe lanzar
