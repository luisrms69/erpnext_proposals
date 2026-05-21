frappe.query_reports["Costos estimados por Designation"] = {
	filters: [
		{
			fieldname: "designation",
			label: __("Designation"),
			fieldtype: "Link",
			options: "Designation",
		},
		{
			fieldname: "status",
			label: __("Estado"),
			fieldtype: "Select",
			options: "\nok\nwarning\nsin_datos",
		},
		{
			fieldname: "source",
			label: __("Fuente"),
			fieldtype: "Select",
			options: "\nactivity_cost\ntimesheet\nsalary",
		},
	],

	onload(report) {
		report.page.add_inner_button(__("Recalcular Costos"), () => {
			frappe.confirm(
				__("¿Recalcular la matriz de costos por Designation desde empleados activos?"),
				() => {
					frappe.show_alert({ message: __("Recalculando..."), indicator: "blue" });
					frappe.call({
						method: "erpnext_proposals.erpnext_proposals.utils.cost_matrix.rebuild_cost_matrix",
						callback(r) {
							if (r.message) {
								const { created, updated, skipped } = r.message;
								frappe.show_alert(
									{
										message: __(
											"Listo — Creados: {0} | Actualizados: {1} | Omitidos: {2}",
											[created, updated, skipped]
										),
										indicator: "green",
									},
									5
								);
								report.refresh();
							}
						},
					});
				}
			);
		});
	},
};
