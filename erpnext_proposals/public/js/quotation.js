// Patch ERPNext's QuotationController to suppress "Update Items" on proposals.
// ERPNext adds this button inside its own controller.refresh(), which runs before
// frappe.ui.form.on handlers. Patching here ensures removal after the button is added.
frappe.ui.form.on("Quotation", "onload", function (frm) {
	const ctrl = frm.cscript;
	if (!ctrl || ctrl.__proposal_patch_applied) return;
	const _origRefresh = ctrl.refresh.bind(ctrl);
	ctrl.refresh = function (...args) {
		_origRefresh(...args);
		if (frm.doc.proposal_group && frm.doc.docstatus === 1) {
			frm.remove_custom_button(__("Update Items"));
		}
	};
	ctrl.__proposal_patch_applied = true;
});

// Reload attachments when server signals PDFs are ready (after_commit)
frappe.realtime.on("erpnext_proposals_pdfs_attached", (data) => {
	if (cur_frm && cur_frm.doctype === data.doctype && cur_frm.docname === data.name) {
		cur_frm.attachments.refresh();
		cur_frm.reload_doc();
	}
});

frappe.ui.form.on("Quotation", {
	// Reload after workflow transition so PDF attachments appear immediately
	after_workflow_action(frm) {
		if (frm.doc.proposal_group) {
			frm.reload_doc();
		}
	},

	refresh(frm) {
		// proposal_version and proposal_group are server-assigned — lock UI editing
		frm.set_df_property("proposal_version", "read_only", 1);
		if (frm.doc.proposal_version >= 1) {
			frm.set_df_property("proposal_group", "read_only", 1);
		}

		// Submitted proposals: hide Cancel button
		// Update Items: blocked in backend (before_update_after_submit). UI hide pending —
		// button origin unknown without runtime inspection; see TODO in PR.
		// Sales Order: left visible — Aprobada → SO is an accepted flow.
		if (frm.doc.docstatus === 1 && frm.doc.proposal_group) {
			frm.page.btn_secondary.hide();
		}

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

		// Button: Nueva versión — submitted + Rechazada + not yet superseded
		if (
			frm.doc.docstatus === 1 &&
			frm.doc.workflow_state === "Rechazada" &&
			frm.doc.proposal_group &&
			!frm.doc.superseded_by_proposal
		) {
			frm.add_custom_button(
				__("Crear nueva versión"),
				() => {
					const fields = [
						{
							fieldname: "reason",
							label: __("Motivo de revisión"),
							fieldtype: "Small Text",
							reqd: 1,
						},
						{
							fieldname: "summary",
							label: __("Resumen de cambios"),
							fieldtype: "Small Text",
						},
					];
					frappe.prompt(
						fields,
						({ reason, summary }) => {
							frappe.call({
								method: "erpnext_proposals.erpnext_proposals.utils.proposal_versioning.create_new_proposal_version",
								args: {
									quotation_name: frm.doc.name,
									reason,
									summary: summary || "",
								},
								freeze: true,
								freeze_message: __("Creando nueva versión…"),
								callback(r) {
									if (r.message) {
										frappe.set_route("Form", "Quotation", r.message);
									}
								},
							});
						},
						__("Nueva versión de propuesta"),
						__("Crear versión")
					);
				},
				__("Propuesta")
			);
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
