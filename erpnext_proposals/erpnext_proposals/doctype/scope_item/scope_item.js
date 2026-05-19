frappe.ui.form.on("Scope Item", {
	refresh(frm) {
		if (frm.doc.erpnext_item) {
			frm.add_custom_button(__("Ver Item ERPNext"), () => {
				frappe.set_route("Form", "Item", frm.doc.erpnext_item);
			});
		}
	},
});
