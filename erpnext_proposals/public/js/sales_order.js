frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		// ERPNext 16: prevdoc_doctype removed, use prevdoc_docname directly
		const has_quotation = (frm.doc.items || []).some((item) => item.prevdoc_docname);
		if (!has_quotation) return;

		frm.add_custom_button(
			__("Crear Proyecto desde Propuesta"),
			() => {
				frappe.confirm(
					__("¿Crear Proyecto y Tasks desde los Scope Items de la propuesta?"),
					() => {
						frappe.call({
							method: "erpnext_proposals.erpnext_proposals.utils.project.create_project_from_proposal",
							args: { sales_order_name: frm.doc.name },
							callback(r) {
								if (r.message) {
									const { project, tasks_created, tasks_skipped } = r.message;
									frappe.msgprint(
										__(
											"Proyecto creado: {0}<br>Tasks nuevas: {1} | Omitidas (ya existían): {2}",
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
	},
});
