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

		// Button: Create Project — only when submitted with scope items
		if (
			frm.doc.docstatus === 1 &&
			frm.doc.proposal_template &&
			frm.doc.quotation_scope_items &&
			frm.doc.quotation_scope_items.length > 0
		) {
			const label = frm.doc.proposal_project
				? __("Ver / Actualizar Proyecto")
				: __("Crear Proyecto desde Propuesta");

			frm.add_custom_button(
				label,
				() => {
					frappe.confirm(
						__("¿Crear Proyecto y Tasks desde los Scope Items de esta propuesta?"),
						() => {
							frappe.call({
								method: "erpnext_proposals.erpnext_proposals.utils.project.create_project_from_quotation",
								args: { quotation_name: frm.doc.name },
								callback(r) {
									if (r.message) {
										const { project, tasks_created, tasks_skipped } =
											r.message;
										frappe.msgprint(
											__(
												"Proyecto: {0}<br>Tasks nuevas: {1} | Omitidas: {2}",
												[
													`<a href="/app/project/${project}">${project}</a>`,
													tasks_created,
													tasks_skipped,
												]
											)
										);
										frm.reload_doc();
									}
								},
							});
						}
					);
				},
				__("Propuesta")
			);
		}
	},
});
