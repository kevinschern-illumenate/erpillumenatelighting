// Copyright (c) ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Team Commissions"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			// Default: first day of last month
			default: frappe.datetime.add_months(frappe.datetime.month_start(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			// Default: last day of last month
			default: frappe.datetime.add_days(frappe.datetime.month_start(), -1),
			reqd: 1,
		},
		{
			fieldname: "payment_status",
			label: __("Payment Status"),
			fieldtype: "Select",
			options: [
				"Paid",
				"Due",
				"All",
			].join("\n"),
			default: "Paid",
			reqd: 1,
		},
		{
			fieldname: "sales_person",
			label: __("Sales Person"),
			fieldtype: "Link",
			options: "Sales Person",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "group_by_sales_person",
			label: __("Group by Sales Person"),
			fieldtype: "Check",
			default: 1,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data._is_group_header) {
			value = `<span style="font-weight:600;">${value}</span>`;
		}
		return value;
	},
};
