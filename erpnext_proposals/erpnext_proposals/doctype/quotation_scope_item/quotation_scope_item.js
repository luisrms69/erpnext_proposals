frappe.ui.form.on("Quotation Scope Item", {
	scope_item(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.scope_item) return;

		frappe.db.get_doc("Scope Item", row.scope_item).then((doc) => {
			// Freeze: copy catalog values at selection time.
			// After this point the user can edit freely — changes to
			// the Scope Item catalog will NOT affect this Quotation.
			frappe.model.set_value(cdt, cdn, {
				code: doc.code,
				title: doc.title,
				description: doc.description,
				deliverable: doc.deliverable,
				phase: doc.phase,
				item_code: doc.erpnext_item,
				activity_type: doc.default_activity_type,
				designation: doc.default_designation,
				estimated_hours: doc.estimated_hours,
			});
		});
	},
});
