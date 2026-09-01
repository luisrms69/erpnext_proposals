# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Capacidad SOW (tercer documento oficial) — datos genéricos.

Cubre la lógica pura y reutilizable: resolución del Print Format SOW desde la plantilla y la
generalización de portada separada (``separate_cover_page``) para cualquier documento oficial
designado por la plantilla (comercial o SOW), sin nombres hardcodeados. No renderiza PDFs.

Usa ``unittest.TestCase`` (patrón del repo para pruebas que tocan Quotation) para evitar el preload
global de test-records de ERPNext; no inserta Quotations (solo ``new_doc``)."""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.utils.print_format import (
	_uses_separate_cover,
	resolve_sow_print_format,
)

_COM_PF = "_TEST Commercial PF"
_SOW_PF = "_TEST SOW PF"
_TMPL_SOW = "_TEST Template with SOW"
_TMPL_NO_SOW = "_TEST Template without SOW"
_TMPL_NO_COVER = "_TEST Template SOW no cover"


def _ensure_print_format(name: str) -> None:
	if not frappe.db.exists("Print Format", name):
		frappe.get_doc(
			{
				"doctype": "Print Format",
				"name": name,
				"doc_type": "Quotation",
				"print_format_type": "Jinja",
				"html": "<div>generic</div>",
			}
		).insert(ignore_permissions=True)


def _ensure_template(name: str, sow_pf: str | None, separate_cover: int) -> None:
	if not frappe.db.exists("Proposal Template", name):
		frappe.get_doc(
			{
				"doctype": "Proposal Template",
				"template_name": name,
				"print_format": _COM_PF,
				"sow_print_format": sow_pf,
				"separate_cover_page": separate_cover,
			}
		).insert(ignore_permissions=True)


class TestSowDocument(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		_ensure_print_format(_COM_PF)
		_ensure_print_format(_SOW_PF)
		_ensure_template(_TMPL_SOW, _SOW_PF, 1)
		_ensure_template(_TMPL_NO_SOW, None, 1)
		_ensure_template(_TMPL_NO_COVER, _SOW_PF, 0)
		frappe.db.commit()  # nosemgrep — fixtures de test

	@classmethod
	def tearDownClass(cls):
		for t in (_TMPL_SOW, _TMPL_NO_SOW, _TMPL_NO_COVER):
			if frappe.db.exists("Proposal Template", t):
				frappe.delete_doc("Proposal Template", t, force=True, ignore_permissions=True)
		for pf in (_COM_PF, _SOW_PF):
			if frappe.db.exists("Print Format", pf):
				frappe.delete_doc("Print Format", pf, force=True, ignore_permissions=True)
		frappe.db.commit()  # nosemgrep — limpieza de fixtures de test

	def _quotation(self, template: str):
		q = frappe.new_doc("Quotation")
		q.proposal_template = template
		q.proposal_print_format = _COM_PF
		return q

	def test_resolve_sow_from_template(self):
		self.assertEqual(resolve_sow_print_format(self._quotation(_TMPL_SOW)), _SOW_PF)

	def test_resolve_sow_none_when_unset(self):
		self.assertIsNone(resolve_sow_print_format(self._quotation(_TMPL_NO_SOW)))

	def test_resolve_sow_none_without_template(self):
		self.assertIsNone(resolve_sow_print_format(frappe.new_doc("Quotation")))

	def test_separate_cover_generalized_to_commercial_and_sow(self):
		"""El flag separate_cover_page aplica por igual al PF comercial y al SOW designados por la
		plantilla — sin ramas por tipo ni nombres hardcodeados."""
		q = self._quotation(_TMPL_SOW)
		self.assertTrue(_uses_separate_cover(q, _COM_PF))
		self.assertTrue(_uses_separate_cover(q, _SOW_PF))

	def test_separate_cover_excludes_non_designated_pf(self):
		# Un PF que la plantilla NO designa (p. ej. Rentabilidad Estimada) no usa portada separada.
		self.assertFalse(_uses_separate_cover(self._quotation(_TMPL_SOW), "Rentabilidad Estimada"))

	def test_separate_cover_off_when_flag_disabled(self):
		q = self._quotation(_TMPL_NO_COVER)
		self.assertFalse(_uses_separate_cover(q, _COM_PF))
		self.assertFalse(_uses_separate_cover(q, _SOW_PF))


if __name__ == "__main__":
	unittest.main()
