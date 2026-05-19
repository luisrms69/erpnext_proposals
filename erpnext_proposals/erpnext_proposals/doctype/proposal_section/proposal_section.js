frappe.ui.form.on("Proposal Section", {
	section_name(frm) {
		if (!frm.doc.title) {
			frm.set_value("title", frm.doc.section_name);
		}
	},
});
