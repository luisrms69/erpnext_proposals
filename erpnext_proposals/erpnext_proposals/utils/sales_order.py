import frappe


def on_sales_order_validate(doc, method=None):
	_sync_project_from_quotation(doc)


def on_sales_order_submit(doc, method=None):
	_link_project_to_sales_order(doc)


def _sync_project_from_quotation(doc):
	"""Auto-fill SO.project and cost_center from the Quotation's proposal fields."""
	quotation_name = next(
		(item.prevdoc_docname for item in doc.items if item.prevdoc_docname),
		None,
	)
	if not quotation_name:
		return

	proposal_project, proposal_cost_center = frappe.db.get_value(
		"Quotation", quotation_name, ["proposal_project", "proposal_cost_center"]
	) or (None, None)

	# Fill SO.project if not already set
	if not doc.project and proposal_project and frappe.db.exists("Project", proposal_project):
		doc.project = proposal_project

	# Fill SO.cost_center (header) and propagate to items
	if proposal_cost_center:
		if not doc.cost_center:
			doc.cost_center = proposal_cost_center
		for item in doc.items:
			if not item.cost_center:
				item.cost_center = proposal_cost_center

	# Ensure Project.cost_center matches if project exists
	if doc.project and proposal_cost_center:
		project_cc = frappe.db.get_value("Project", doc.project, "cost_center")
		if not project_cc:
			frappe.db.set_value(
				"Project", doc.project, "cost_center", proposal_cost_center, update_modified=False
			)


def _link_project_to_sales_order(doc):
	"""After SO is submitted, store SO reference in the Project."""
	if not doc.project:
		return

	current = frappe.db.get_value("Project", doc.project, "sales_order")
	if not current:
		frappe.db.set_value("Project", doc.project, "sales_order", doc.name, update_modified=False)
