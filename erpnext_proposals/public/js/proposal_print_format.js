// Helper CENTRAL para los campos Link de Print Format de propuestas.
// Lo usan por igual `Quotation.proposal_print_format` y `Proposal Template.print_format`:
// una sola query de elegibilidad (servidor) y un solo warning de referencia obsoleta.
// No duplicar la lógica de filtro/aviso en los formularios.
frappe.provide("erpnext_proposals.print_format");

erpnext_proposals.print_format = {
	// Restringe el campo Link a Print Formats elegibles (doc_type=Quotation, disabled=0) usando la
	// query central del servidor. Fuente única de elegibilidad.
	set_query(frm, fieldname) {
		if (!frm.get_field(fieldname)) return;
		frm.set_query(fieldname, () => ({
			query: "erpnext_proposals.erpnext_proposals.utils.print_format.get_proposal_print_formats",
		}));
	},

	// Avisa (una sola consulta al cargar) si el valor actual del campo apunta a un Print Format
	// obsoleto/ inválido. No reemplaza el valor automáticamente.
	warn_if_obsolete(frm, fieldname) {
		const field = frm.get_field(fieldname);
		if (!field) return;
		const value = frm.doc[fieldname];
		const clear = () => field.set_description(field.df.__base_description || "");
		if (field.df.__base_description === undefined) {
			field.df.__base_description = field.df.description || "";
		}
		if (!value) {
			clear();
			return;
		}
		frappe.call({
			method: "erpnext_proposals.erpnext_proposals.utils.print_format.get_print_format_status",
			args: { pf_name: value },
			callback(r) {
				const st = r.message;
				if (!st || st.status === "ok") {
					clear();
					return;
				}
				if (st.status === "disabled") {
					field.set_description(
						`<span style="color:var(--yellow-600,#b45309)">${__(
							"Este Print Format está obsoleto. Selecciona una versión vigente."
						)}</span>`
					);
				} else if (st.status === "missing") {
					field.set_description(
						`<span style="color:var(--red-600,#c0392b)">${__(
							"El Print Format referenciado ya no existe. La referencia no es válida; selecciona una versión vigente."
						)}</span>`
					);
					frm.dashboard.set_headline(
						__(
							"El Print Format de este template ya no existe. Selecciona una versión vigente."
						),
						"red"
					);
				} else if (st.status === "wrong_doctype") {
					field.set_description(
						`<span style="color:var(--red-600,#c0392b)">${__(
							"El Print Format referenciado no es válido para propuestas (no pertenece a Quotation)."
						)}</span>`
					);
				}
			},
		});
	},
};
