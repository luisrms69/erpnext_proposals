"""Alcance específico manual por línea de Quotation (`proposal_specific_scope`).

Verifica: editable/persistente en Borrador; sobrevive a resync y a _copy_item_proposal_fields(force);
se congela al someter; una edición normal post-submit es rechazada; se hereda a la nueva versión
(editable) sin alterar la anterior; e independiente por línea (mismo Item repetido).

Datos ficticios; nunca contenido de cliente. El campo es entrada manual: NO proviene del Item ni del
catálogo, y NO está en _FROZEN_ITEM_FIELDS ni _CATALOG_CONTROLLED_FIELDS.
"""

import unittest

import frappe

from erpnext_proposals.erpnext_proposals.tests.fiscal_year import (
	cleanup_fiscal_year,
	ensure_current_fiscal_year,
)
from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import create_new_proposal_version
from erpnext_proposals.erpnext_proposals.utils.quotation import (
	_copy_item_proposal_fields,
	resync_scope_from_catalog,
)

TEMPLATE = "_Test SS Template"
ITEM = "_Test SS Item"
PHASE = "_SSP1"


class TestProposalSpecificScope(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from erpnext_proposals.erpnext_proposals.tests.company import (
			get_test_company,
			get_test_item_group,
			get_test_price_list,
		)

		cls.company = get_test_company()
		if not cls.company:
			raise unittest.SkipTest("No Company found on test site.")
		# El test de líneas independientes repite el mismo Item; habilitarlo en el site de pruebas.
		cls._prev_allow_multi = frappe.db.get_single_value("Selling Settings", "allow_multiple_items")
		frappe.db.set_single_value("Selling Settings", "allow_multiple_items", 1)
		cls._quotations = []
		cls._created_fy = ensure_current_fiscal_year()
		if not frappe.db.exists("Proposal Phase", PHASE):
			frappe.get_doc(
				{
					"doctype": "Proposal Phase",
					"phase_code": PHASE,
					"phase_name": "Fase SS",
					"sequence": 10,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {}, "name")
		if not frappe.db.exists("Customer", "_Test SS Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test SS Customer",
					"customer_group": cg,
					"territory": terr,
				}
			).insert(ignore_permissions=True)
		cls.customer = "_Test SS Customer"
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
		ig = get_test_item_group()
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": ITEM,
					"item_group": ig,
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"is_sales_item": 1,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.get_doc(
				{"doctype": "Proposal Template", "template_name": TEMPLATE, "description": "t"}
			).insert(ignore_permissions=True)
		cls.cost_center = frappe.db.get_value("Cost Center", {"is_group": 0}, "name")
		# Price List de venta explícita (MXN): el site fresco de CI no siembra ninguna, así que
		# Quotation.selling_price_list/price_list_currency quedarían vacíos y el save() sin
		# ignore_mandatory fallaría. Se setea en la Quotation (ver _make_quotation), no por default del site.
		cls.selling_price_list = get_test_price_list()
		if not frappe.db.exists("Scope Item", "_SS_S1"):
			frappe.get_doc(
				{
					"doctype": "Scope Item",
					"code": "_SS_S1",
					"title": "_SS_S1",
					"sequence": 10,
					"erpnext_item": ITEM,
					"phase": PHASE,
					"enabled": 1,
					"visible_in_proposal": 1,
					"estimated_hours": 4,
				}
			).insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		for q in frappe.get_all("Quotation", filters={"proposal_group": ["like", "SS-%"]}, pluck="name"):
			try:
				doc = frappe.get_doc("Quotation", q)
				if doc.docstatus == 1:
					doc.flags.ignore_linked_doctypes = True
					doc.cancel()
				frappe.delete_doc("Quotation", q, force=True, ignore_permissions=True)
			except Exception:
				pass
		for c in frappe.get_all("Scope Item", filters={"code": ["like", "_SS_%"]}, pluck="name"):
			frappe.delete_doc("Scope Item", c, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Template", TEMPLATE):
			frappe.delete_doc("Proposal Template", TEMPLATE, force=True, ignore_permissions=True)
		if frappe.db.exists("Proposal Phase", PHASE):
			frappe.delete_doc("Proposal Phase", PHASE, force=True, ignore_permissions=True)
		frappe.db.set_single_value(
			"Selling Settings", "allow_multiple_items", getattr(cls, "_prev_allow_multi", 0) or 0
		)
		cleanup_fiscal_year(getattr(cls, "_created_fy", None))
		super().tearDownClass()

	def _draft(self, n_lines=1):
		items = [
			{"item_code": ITEM, "item_name": ITEM, "qty": 1, "rate": 1000, "uom": "Nos"}
			for _ in range(n_lines)
		]
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"proposal_group": "SS-" + frappe.generate_hash(length=6),
				"company": self.company,
				"currency": "MXN",
				"selling_price_list": self.selling_price_list,
				"transaction_date": frappe.utils.today(),
				"proposal_template": TEMPLATE,
				"proposal_cost_center": self.cost_center,
				"proposal_title": "SS " + frappe.generate_hash(length=4),
				"items": items,
			}
		)
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.__class__._quotations.append(doc.name)
		return frappe.get_doc("Quotation", doc.name)

	def _submit_rejected(self, doc):
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.submit()
		frappe.db.set_value("Quotation", doc.name, "workflow_state", "Rechazada", update_modified=False)
		return frappe.get_doc("Quotation", doc.name)

	# 1
	def test_editable_and_persists_in_draft(self):
		doc = self._draft()
		doc.items[0].proposal_specific_scope = "<p>Alcance específico de prueba A</p>"
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertEqual(doc.items[0].proposal_specific_scope, "<p>Alcance específico de prueba A</p>")

	# 2
	def test_resync_preserves_value(self):
		doc = self._draft()
		doc.items[0].proposal_specific_scope = "<p>manual resync</p>"
		doc.save(ignore_permissions=True)
		resync_scope_from_catalog(doc.name)
		doc.reload()
		self.assertEqual(doc.items[0].proposal_specific_scope, "<p>manual resync</p>")

	# 3
	def test_copy_item_proposal_fields_force_does_not_touch(self):
		doc = self._draft()
		doc.items[0].proposal_specific_scope = "<p>no tocar</p>"
		doc.save(ignore_permissions=True)
		_copy_item_proposal_fields(doc, force=True)
		self.assertEqual(doc.items[0].proposal_specific_scope, "<p>no tocar</p>")

	# 4 + 5
	def test_submit_freezes_and_blocks_edit(self):
		doc = self._draft()
		doc.items[0].proposal_specific_scope = "<p>congelado</p>"
		doc.save(ignore_permissions=True)
		doc = self._submit_rejected(doc)
		# congelado en la línea sometida
		self.assertEqual(
			frappe.db.get_value("Quotation Item", doc.items[0].name, "proposal_specific_scope"),
			"<p>congelado</p>",
		)
		# una edición normal post-submit (sin transición de workflow) es rechazada
		doc.items[0].proposal_specific_scope = "<p>intento cambiar</p>"
		with self.assertRaises(Exception):
			doc.save(ignore_permissions=True)

	# 6 + 7
	def test_new_version_copies_and_editable(self):
		doc = self._draft()
		doc.items[0].proposal_specific_scope = "<p>version 1</p>"
		doc.save(ignore_permissions=True)
		doc = self._submit_rejected(doc)
		new_name = create_new_proposal_version(doc.name, reason="prueba de versión", summary="")
		new_doc = frappe.get_doc("Quotation", new_name)
		# heredado
		self.assertEqual(new_doc.items[0].proposal_specific_scope, "<p>version 1</p>")
		# anterior intacto
		self.assertEqual(
			frappe.db.get_value("Quotation Item", doc.items[0].name, "proposal_specific_scope"),
			"<p>version 1</p>",
		)
		# nuevo Borrador editable
		self.assertEqual(new_doc.docstatus, 0)
		new_doc.items[0].proposal_specific_scope = "<p>version 2</p>"
		new_doc.save(ignore_permissions=True)
		new_doc.reload()
		self.assertEqual(new_doc.items[0].proposal_specific_scope, "<p>version 2</p>")

	# 8
	def test_independent_per_line_same_item(self):
		doc = self._draft(n_lines=2)
		doc.items[0].proposal_specific_scope = "<p>línea 1</p>"
		doc.items[1].proposal_specific_scope = "<p>línea 2</p>"
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertEqual(doc.items[0].proposal_specific_scope, "<p>línea 1</p>")
		self.assertEqual(doc.items[1].proposal_specific_scope, "<p>línea 2</p>")
