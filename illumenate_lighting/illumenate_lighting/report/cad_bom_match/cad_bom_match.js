// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.query_reports["CAD BOM Match"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("Ordered from"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -90),
		},
		{
			fieldname: "to_date",
			label: __("Ordered to"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "only_cad",
			label: __("Only drawing imports"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "source_tool",
			label: __("Drawing tool"),
			fieldtype: "Select",
			options: ["", "autocad", "dxf", "bluebeam", "web"].join("\n"),
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
	],
};
