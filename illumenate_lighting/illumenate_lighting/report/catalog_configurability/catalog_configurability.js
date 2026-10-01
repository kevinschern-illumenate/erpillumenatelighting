// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.query_reports["Catalog Configurability"] = {
	filters: [
		{
			fieldname: "product_type",
			label: __("Product Type"),
			fieldtype: "Select",
			options: ["", "Fixture Template", "LED Tape", "LED Neon", "LED Sheet"],
		},
		{
			fieldname: "only_problems",
			label: __("Only products that cannot be configured"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "include_inactive",
			label: __("Include inactive products"),
			fieldtype: "Check",
			default: 0,
		},
	],

	onload(report) {
		if (!frappe.user.has_role(["System Manager", "ilL Catalog Publisher"])) return;
		report.page.add_inner_button(__("Preview repair"), () => run_catalog_repair(report, true));
		report.page.add_inner_button(__("Apply repair"), () => {
			frappe.confirm(
				__("Link each product to the active template that points at it and mark it configurable? Saving regenerates the product's configurator options and marks synced products as pending Webflow sync."),
				() => run_catalog_repair(report, false)
			);
		});
	},
};

function run_catalog_repair(report, dry_run) {
	frappe.call({
		method: "illumenate_lighting.illumenate_lighting.portal.catalog_repair.repair",
		type: "POST",
		args: { dry_run: dry_run ? 1 : 0 },
		freeze: true,
		callback(r) {
			const result = r.message || {};
			const row = (cells) => "<tr>" + cells.map((cell) => "<td>" + frappe.utils.escape_html(String(cell)) + "</td>").join("") + "</tr>";
			const section = (title, rows) => rows.length
				? "<h5>" + frappe.utils.escape_html(title) + "</h5><table class='table table-bordered table-sm'>" + rows.join("") + "</table>"
				: "";
			const changes = (result.changes || []).map((entry) => row([
				entry.product_name || entry.product,
				Object.entries(entry.changes).map(([field, value]) => field + " = " + value).join(", "),
			]));
			const conflicts = (result.conflicts || []).map((entry) => row([entry.product_name || entry.product, entry.message]));
			const errors = (result.errors || []).map((entry) => row([entry.product_name || entry.product, entry.message]));
			const body = section(dry_run ? __("Would change") : __("Changed"), changes)
				+ section(__("Needs a manual decision"), conflicts)
				+ section(__("Failed"), errors);
			frappe.msgprint({
				title: dry_run ? __("Repair preview") : __("Repair applied"),
				message: body || __("Nothing to repair: no active template points at a product that is missing its link."),
				wide: true,
			});
			if (!dry_run) report.refresh();
		},
	});
}
