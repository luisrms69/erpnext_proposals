frappe.ui.form.on("Quotation Scope Item", {
	scope_item(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.scope_item) return;

		frappe.db.get_doc("Scope Item", row.scope_item).then((doc) => {
			// Freeze: copy catalog values at selection time.
			// After this point the user can edit freely — changes to
			// the Scope Item catalog will NOT affect this Quotation.
			frappe.model.set_value(cdt, cdn, {
				sequence: doc.sequence,
				code: doc.code,
				title: doc.title,
				description: doc.description,
				deliverable: doc.deliverable,
				phase: doc.phase,
				item_code: doc.erpnext_item,
				activity_type: doc.default_activity_type,
				designation: doc.default_designation,
				estimated_hours: doc.estimated_hours,
				is_internal_cost_task: doc.is_internal_cost_task,
				// Valor inicial de include_in_proposal desde el catálogo (visible_in_proposal).
				include_in_proposal: doc.visible_in_proposal ? 1 : 0,
			});
		});
	},
});
