frappe.ui.form.on("Proposal Template", {
	refresh(frm) {
		frm.fields_dict.sections.grid.get_field("proposal_section").get_query = () => ({
			filters: { enabled: 1 },
		});
	},
});

frappe.ui.form.on("Proposal Template Section", {
	sections_add(frm, cdt, cdn) {
		// Pre-fill sequence as next multiple of 10
		const rows = frm.doc.sections || [];
		const maxSeq = rows.reduce((m, r) => (r.sequence > m ? r.sequence : m), 0);
		frappe.model.set_value(cdt, cdn, "sequence", maxSeq + 10);
	},
});
