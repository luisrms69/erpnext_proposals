frappe.ui.form.on("Quotation", {
	refresh(frm) {
		// Filter: only enabled Scope Items in the inline grid
		if (frm.fields_dict.quotation_scope_items) {
			frm.fields_dict.quotation_scope_items.grid.get_field("scope_item").get_query = () => ({
				filters: { enabled: 1 },
			});
		}
	},
});
