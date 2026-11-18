// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.query_reports["Build Points Calibration"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("Completed From"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -90),
		},
		{
			fieldname: "to_date",
			label: __("Completed To"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "only_timed",
			label: __("Only Work Orders With Time"),
			fieldtype: "Check",
			default: 1,
		},
	],
	onload(report) {
		if (!frappe.user.has_role(["System Manager", "Manufacturing Manager"])) return;
		report.page.add_inner_button(__("Apply Suggested Weights"), () => {
			const from_date = report.get_filter_value("from_date");
			const to_date = report.get_filter_value("to_date");
			frappe.confirm(
				__("Replace the weights and points per person per day in Production Settings with the suggested values? Stored build points are re-scored."),
				() =>
					frappe
						.call("illumenate_lighting.illumenate_lighting.api.build_operations.apply_calibration", { from_date, to_date })
						.then(() => {
							frappe.show_alert({ message: __("Production Settings updated"), indicator: "green" });
							report.refresh();
						})
			);
		});
	},
};
