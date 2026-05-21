import frappe
from frappe.utils import flt, now_datetime


def on_quotation_validate(doc, method=None):
	if not doc.proposal_template:
		return
	_generate_scope_items(doc)


def _generate_scope_items(doc):
	existing = {
		(row.item_code, row.scope_item)
		for row in (doc.quotation_scope_items or [])
		if row.item_code and row.scope_item
	}

	for item in doc.items or []:
		if not item.item_code:
			continue

		scope_items = frappe.get_all(
			"Scope Item",
			filters={"erpnext_item": item.item_code, "enabled": 1},
			fields=[
				"name",
				"sequence",
				"code",
				"title",
				"description",
				"deliverable",
				"phase",
				"default_activity_type",
				"default_designation",
				"estimated_hours",
			],
			order_by="phase asc, sequence asc",
		)

		for si in scope_items:
			if (item.item_code, si.name) in existing:
				continue
			doc.append(
				"quotation_scope_items",
				{
					"scope_item": si.name,
					"item_code": item.item_code,
					"sequence": si.sequence,
					"code": si.code,
					"title": si.title,
					"description": si.description,
					"deliverable": si.deliverable,
					"phase": si.phase,
					"activity_type": si.default_activity_type,
					"designation": si.default_designation,
					"estimated_hours": si.estimated_hours,
					"include_in_proposal": 1,
					"auto_generated": 1,
				},
			)
			existing.add((item.item_code, si.name))


def on_quotation_before_submit(doc, method=None):
	"""Freeze costing rates in Quotation Scope Items at submit time.

	Called via before_submit hook. Reads current Proposal Cost Matrix for each
	scope item marked include_in_proposal and stores the rate, source and lock
	timestamp. Submitted quotations use these frozen values for profitability;
	Draft quotations always recalculate from the current matrix.
	"""
	from erpnext_proposals.erpnext_proposals.utils.cost_matrix import get_designation_cost

	now = now_datetime()
	for row in doc.quotation_scope_items or []:
		if not row.include_in_proposal:
			continue
		rate, source = get_designation_cost(row.designation, row.activity_type)
		row.costing_rate = flt(rate)
		row.rate_source = source
		row.rate_locked = 1
		row.rate_locked_on = now
