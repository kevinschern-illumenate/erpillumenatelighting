// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.query_reports["Fixture Readiness"] = {
	filters: [
		{
			fieldname: "not_ready_only",
			label: __("Not ready only"),
			fieldtype: "Check",
			default: 1,
		},
	],
};
