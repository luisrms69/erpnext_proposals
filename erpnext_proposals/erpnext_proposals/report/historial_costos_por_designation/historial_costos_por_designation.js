frappe.query_reports["Historial de costos por Designation"] = {
	filters: [
		{
			fieldname: "designation",
			label: __("Designation"),
			fieldtype: "Link",
			options: "Designation",
		},
		{
			fieldname: "activity_type",
			label: __("Tipo de Actividad"),
			fieldtype: "Link",
			options: "Activity Type",
		},
		{
			fieldname: "from_date",
			label: __("Desde"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("Hasta"),
			fieldtype: "Date",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "change_amount" && data) {
			const color = data.change_amount > 0 ? "red" : data.change_amount < 0 ? "green" : "";
			if (color) value = `<span style="color:${color}">${value}</span>`;
		}
		if (column.fieldname === "change_percent" && data && data.change_percent == null) {
			value = "<span style='color:#aaa'>N/A</span>";
		}
		return value;
	},
};
