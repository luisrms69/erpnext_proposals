frappe.ui.form.on("Proposal Template", {
	refresh(frm) {
		frm.fields_dict.sections.grid.get_field("proposal_section").get_query = () => ({
			filters: { enabled: 1 },
		});
		// Mismo selector central que Quotation.proposal_print_format: solo formatos vigentes de Quotation.
		erpnext_proposals.print_format.set_query(frm, "print_format");
		// Aviso si el template sigue apuntando a un Print Format obsoleto / inexistente (no lo reemplaza).
		erpnext_proposals.print_format.warn_if_obsolete(frm, "print_format");
	},
	print_format(frm) {
		// Al cambiar el valor, refrescar el aviso de elegibilidad.
		erpnext_proposals.print_format.warn_if_obsolete(frm, "print_format");
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
