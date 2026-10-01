// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.query_reports["Product Finder Coverage"] = {
	filters: [
		{
			fieldname: "question",
			label: __("Question"),
			fieldtype: "Link",
			options: "ilL-Finder-Question",
		},
		{
			fieldname: "issue",
			label: __("Issue"),
			fieldtype: "Select",
			options: ["", "Answer not mapped", "ERP value not reachable", "Condition on inactive question", "LED package without spectrum type"],
		},
	],
};
