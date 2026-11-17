// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.query_reports["Tape Neon Repricing Preview"] = {
	filters: [
		{
			fieldname: "status",
			label: __("Schedule status"),
			fieldtype: "Select",
			options: "\nDRAFT\nREADY\nQUOTED",
		},
		{
			fieldname: "only_changed",
			label: __("Only lines whose price changes"),
			fieldtype: "Check",
			default: 1,
		},
	],
};
