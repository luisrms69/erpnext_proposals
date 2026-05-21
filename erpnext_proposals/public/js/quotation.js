frappe.ui.form.on("Quotation", {
	refresh(frm) {
		if (frm.fields_dict.quotation_scope_items) {
			frm.fields_dict.quotation_scope_items.grid.get_field("scope_item").get_query = () => ({
				filters: { enabled: 1 },
			});
		}

		// Regenerar alcance: only in Borrador (docstatus=0) — document is editable
		if (
			!frm.is_new() &&
			frm.doc.proposal_template &&
			frm.doc.docstatus === 0 &&
			frm.doc.workflow_state === "Borrador"
		) {
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

		// PDF buttons — available in all states (including Borrador for preview)
		if (!frm.is_new()) {
			frm.add_custom_button(
				__("Imprimir Propuesta Comercial"),
				() => {
					const url = `/printview?doctype=Quotation&name=${encodeURIComponent(
						frm.doc.name
					)}&format=Propuesta%20Comercial&no_letterhead=0`;
					window.open(url, "_blank");
				},
				__("Propuesta")
			);

			frm.add_custom_button(
				__("Imprimir Rentabilidad Estimada"),
				() => {
					const url = `/printview?doctype=Quotation&name=${encodeURIComponent(
						frm.doc.name
					)}&format=Rentabilidad%20Estimada&no_letterhead=0`;
					window.open(url, "_blank");
				},
				__("Propuesta")
			);

			// Show attached PDFs if they exist
			frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "File",
					filters: {
						attached_to_doctype: "Quotation",
						attached_to_name: frm.doc.name,
						file_name: ["like", "%.pdf"],
					},
					fields: ["file_name", "file_url"],
					limit: 10,
				},
				callback(r) {
					if (r.message && r.message.length) {
						r.message.forEach((f) => {
							frm.add_custom_button(
								__("↓ {0}", [f.file_name]),
								() => window.open(f.file_url),
								__("Propuesta")
							);
						});
					}
				},
			});
		}

		// Button: Create Project — submitted + Aprobada or Enviada al Cliente
		const _projectStates = ["Aprobada", "Enviada al Cliente"];
		if (
			frm.doc.docstatus === 1 &&
			_projectStates.includes(frm.doc.workflow_state) &&
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
