// Administración de la relación N:N Item ↔ Scope Item DESDE el formulario Item.
// La relación vive físicamente en Scope Item.erpnext_items; aquí se ofrece la UX natural desde Item.

frappe.ui.form.on("Item", {
	refresh(frm) {
		// Solo en un Item ya guardado. Botón DIRECTO en la barra de acciones (no en Actions/Create).
		if (frm.is_new()) return;
		frm.add_custom_button(__("Scope Items"), () => open_scope_items_dialog(frm));
	},
});

function open_scope_items_dialog(frm) {
	const item = frm.doc.name;
	frappe
		.call({
			method: "erpnext_proposals.erpnext_proposals.utils.scope_item_links.get_scope_items_for_item",
			args: { item },
		})
		.then((r) => {
			// Estado local: mapa name -> {code, title}. Arranca con lo actualmente asociado.
			const selected = new Map();
			(r.message || []).forEach((s) =>
				selected.set(s.name, { code: s.code, title: s.title })
			);

			const d = new frappe.ui.Dialog({
				title: __("Scope Items"),
				size: "large",
				fields: [
					{
						fieldname: "add_scope_item",
						label: __("Agregar Scope Item"),
						fieldtype: "Link",
						options: "Scope Item",
						// Solo Scope Items habilitados y que no estén ya seleccionados.
						get_query: () => ({
							filters: {
								enabled: 1,
								name: ["not in", Array.from(selected.keys())],
							},
						}),
					},
					{ fieldname: "lista", fieldtype: "HTML" },
				],
				primary_action_label: __("Guardar"),
				primary_action: () => {
					frappe
						.call({
							method: "erpnext_proposals.erpnext_proposals.utils.scope_item_links.set_scope_items_for_item",
							args: {
								item,
								scope_items: JSON.stringify(Array.from(selected.keys())),
							},
						})
						.then((res) => {
							const m = res.message || {};
							frappe.show_alert({
								message: __(
									"Scope Items actualizados (agregados: {0}, quitados: {1}).",
									[m.added || 0, m.removed || 0]
								),
								indicator: "green",
							});
							d.hide();
						});
				},
			});

			const render = () => {
				const rows = Array.from(selected.entries())
					.map(([name, meta]) => {
						const title = meta.title
							? ` — ${frappe.utils.escape_html(meta.title)}`
							: "";
						return `<tr>
							<td>${frappe.utils.escape_html(meta.code || name)}${title}</td>
							<td style="text-align:right">
								<a class="text-danger sc-remove" data-name="${frappe.utils.escape_html(name)}">${__("Quitar")}</a>
							</td>
						</tr>`;
					})
					.join("");
				const html = selected.size
					? `<table class="table table-bordered"><thead><tr>
							<th>${__("Scope Item")}</th><th style="width:80px"></th></tr></thead>
							<tbody>${rows}</tbody></table>`
					: `<p class="text-muted">${__("Sin Scope Items asociados a este Item.")}</p>`;
				const $w = d.fields_dict.lista.$wrapper.html(html);
				$w.find(".sc-remove").on("click", (e) => {
					selected.delete($(e.currentTarget).data("name").toString());
					render();
				});
			};

			// Al elegir un Scope Item en el Link: agregarlo al estado y limpiar el Link.
			d.fields_dict.add_scope_item.df.onchange = () => {
				const val = d.get_value("add_scope_item");
				if (val && !selected.has(val)) {
					frappe.db.get_value("Scope Item", val, ["code", "title"]).then((g) => {
						const m = g.message || {};
						selected.set(val, { code: m.code || val, title: m.title });
						d.set_value("add_scope_item", "");
						render();
					});
				} else if (val) {
					d.set_value("add_scope_item", "");
				}
			};

			d.show();
			render();
		});
}
