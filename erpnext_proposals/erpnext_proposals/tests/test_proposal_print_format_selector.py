"""Selector central de Print Formats para propuestas + validación de servidor compartida.

Cubre la query única de elegibilidad (doc_type=Quotation, disabled=0), su uso idéntico en
`Quotation.proposal_print_format` y `Proposal Template.print_format`, la detección de referencias
obsoletas para el warning, la validación change-aware de servidor (bloquea ADOPTAR un formato no
elegible sin invalidar referencias históricas no modificadas) y que ADR-0011 no se relaja.
"""

import unittest

import frappe
from frappe.exceptions import ValidationError

from erpnext_proposals.erpnext_proposals.utils.print_format import (
	assert_assignable_print_format,
	get_print_format_status,
	get_proposal_print_formats,
	validate_print_format,
)

PF_OK = "_Test PSP Vigente"
PF_DISABLED = "_Test PSP Obsoleto"
PF_OTHER = "_Test PF Otro DocType"


def _mk_pf(name: str, doc_type: str, disabled: int) -> None:
	if frappe.db.exists("Print Format", name):
		frappe.db.set_value("Print Format", name, {"doc_type": doc_type, "disabled": disabled})
		return
	frappe.get_doc(
		{
			"doctype": "Print Format",
			"name": name,
			"doc_type": doc_type,
			"print_format_type": "Jinja",
			"standard": "No",
			"disabled": disabled,
			"module": "ERPNext Proposals",
			"html": "<div>x</div>",
		}
	).insert(ignore_permissions=True)


class _FakeDoc:
	"""Sustituto ligero de un Document para ejercitar la validación change-aware sin ciclo de guardado."""

	def __init__(self, values: dict, new: bool = False, changed=None):
		self._v = dict(values)
		self._new = new
		self._changed = set(changed or [])

	def get(self, key):
		return self._v.get(key)

	def is_new(self):
		return self._new

	def has_value_changed(self, key):
		return key in self._changed


class TestProposalPrintFormatSelector(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_mk_pf(PF_OK, "Quotation", 0)
		_mk_pf(PF_DISABLED, "Quotation", 1)
		_mk_pf(PF_OTHER, "Sales Invoice", 0)

	@classmethod
	def tearDownClass(cls):
		for n in (PF_OK, PF_DISABLED, PF_OTHER):
			if frappe.db.exists("Print Format", n):
				frappe.delete_doc("Print Format", n, force=True, ignore_permissions=True)
		super().tearDownClass()

	def _query(self, txt=""):
		rows = get_proposal_print_formats("Print Format", txt, "name", 0, 50, {})
		return {r[0] for r in rows}

	# 1 — la query devuelve un Print Format de Quotation activo
	def test_01_query_returns_active_quotation_pf(self):
		self.assertIn(PF_OK, self._query("_Test PSP"))

	# 2 — la query excluye disabled=1
	def test_02_query_excludes_disabled(self):
		self.assertNotIn(PF_DISABLED, self._query("_Test PSP"))

	# 3 — la query excluye Print Formats de otros DocTypes
	def test_03_query_excludes_other_doctypes(self):
		self.assertNotIn(PF_OTHER, self._query("_Test PF"))

	# 4 — la MISMA query sirve para ambos campos (es agnóstica del campo/origen)
	def test_04_same_query_used_for_both_fields(self):
		got = self._query("_Test")
		self.assertIn(PF_OK, got)
		self.assertNotIn(PF_DISABLED, got)
		self.assertNotIn(PF_OTHER, got)

	# 5 — Proposal Template/Quotation con formato válido → status ok (sin warning)
	def test_05_valid_format_no_warning(self):
		self.assertEqual(get_print_format_status(PF_OK)["status"], "ok")

	# 6 — referencia a formato disabled → detectada como obsoleta
	def test_06_disabled_detected_obsolete(self):
		self.assertEqual(get_print_format_status(PF_DISABLED)["status"], "disabled")

	# 7 — referencia inexistente / de otro DocType → detectada
	def test_07_missing_or_wrong_detected(self):
		self.assertEqual(get_print_format_status("_No Existe PF 123")["status"], "missing")
		self.assertEqual(get_print_format_status(PF_OTHER)["status"], "wrong_doctype")

	# 8 — servidor rechaza ADOPTAR un formato disabled en documento nuevo/editable
	def test_08_server_rejects_disabled_on_editable(self):
		with self.assertRaises(ValidationError):
			assert_assignable_print_format(
				_FakeDoc({"proposal_print_format": PF_DISABLED}, new=True), "proposal_print_format"
			)
		with self.assertRaises(ValidationError):
			assert_assignable_print_format(
				_FakeDoc(
					{"proposal_print_format": PF_DISABLED}, new=False, changed=["proposal_print_format"]
				),
				"proposal_print_format",
			)

	# 9 — histórico/congelado conserva una referencia que luego fue deshabilitada (valor no cambiado)
	def test_09_frozen_keeps_later_disabled_reference(self):
		try:
			assert_assignable_print_format(
				_FakeDoc({"proposal_print_format": PF_DISABLED}, new=False, changed=[]),
				"proposal_print_format",
			)
		except ValidationError:
			self.fail("no debe invalidar retroactivamente una referencia histórica no modificada (Quotation)")
		try:
			assert_assignable_print_format(
				_FakeDoc({"print_format": PF_DISABLED}, new=False, changed=[]), "print_format"
			)
		except ValidationError:
			self.fail("un Proposal Template existente no modificado no debe invalidarse")

	# 10 — no se rompe ADR-0011 ni se relaja la elegibilidad
	def test_10_adr0011_and_eligibility_not_relaxed(self):
		from erpnext_proposals import hooks

		pf_events = str(hooks.doc_events.get("Print Format", {}))
		self.assertIn("protect_historical_print_format_on_save", pf_events)
		self.assertIn("protect_historical_print_format_on_trash", pf_events)
		# el validador base sigue rechazando un formato deshabilitado (elegibilidad intacta)
		with self.assertRaises(ValidationError):
			validate_print_format(PF_DISABLED)
