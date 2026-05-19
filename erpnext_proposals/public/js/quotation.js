frappe.ui.form.on("Quotation", {
	refresh(frm) {
		if (frm.fields_dict.quotation_scope_items) {
			frm.fields_dict.quotation_scope_items.grid.get_field("scope_item").get_query = () => ({
				filters: { enabled: 1 },
			});
		}

		if (!frm.is_new() && frm.doc.proposal_template) {
			frm.add_custom_button(
				__("Regenerar alcance"),
				() => {
					frappe.confirm(
						__(
							"¿Regenerar alcance desde Items? Solo se agregarán combinaciones nuevas. No se borrarán filas existentes."
						),
						() => {
							frm.save().then(() => frm.reload_doc());
						}
					);
				},
				__("Propuesta")
			);
		}
	},
});
