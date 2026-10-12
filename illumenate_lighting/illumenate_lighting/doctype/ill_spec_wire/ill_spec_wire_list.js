// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

// Import reviewed field wire from tools/seed_imports/field_wire_TEMPLATE.csv (System Designer WP-1.4).
// Every import is checked first (dry run); nothing is written unless every row is valid.
const WIRE_IMPORT_METHOD =
	"illumenate_lighting.illumenate_lighting.system_design.wire_import.import_field_wire";

frappe.listview_settings["ilL-Spec-Wire"] = {
	add_fields: ["is_active", "is_verified"],

	get_indicator(doc) {
		if (!doc.is_active) return [__("Inactive"), "gray", "is_active,=,0"];
		if (!doc.is_verified) return [__("Not verified"), "orange", "is_verified,=,0"];
		return [__("Verified"), "green", "is_verified,=,1"];
	},

	onload(listview) {
		listview.page.add_inner_button(__("Import Field Wire CSV"), () => pick_wire_csv(listview));
	},
};

function pick_wire_csv(listview) {
	const input = document.createElement("input");
	input.type = "file";
	input.accept = ".csv,text/csv";
	input.addEventListener("change", () => {
		const file = input.files && input.files[0];
		if (!file) return;
		file.text().then((text) => run_wire_import(listview, text, true));
	});
	input.click();
}

function run_wire_import(listview, text, dry_run) {
	frappe.call({
		method: WIRE_IMPORT_METHOD,
		args: { csv_text: text, dry_run: dry_run ? 1 : 0 },
		freeze: true,
		freeze_message: dry_run ? __("Checking wire CSV…") : __("Importing field wire…"),
		callback(r) {
			const result = r.message || {};
			if (!result.success) {
				frappe.msgprint({ title: __("Import failed"), message: frappe.utils.escape_html(result.error || ""), indicator: "red" });
				return;
			}
			show_wire_report(listview, text, result.data);
		},
	});
}

function show_wire_report(listview, text, report) {
	const esc = frappe.utils.escape_html;
	const rows = report.rows
		.map(
			(row) => `<tr>
				<td>${row.row}</td>
				<td>${esc(row.item_code || "")}</td>
				<td>${esc(row.item_action)}</td>
				<td>${esc(row.spec_action)}</td>
				<td>${row.problems.length ? row.problems.map(esc).join("<br>") : "✓"}</td>
			</tr>`,
		)
		.join("");
	const summary = report.written
		? __("Imported {0} wire rows.", [report.rows.length])
		: report.invalid
			? __("{0} of {1} rows need fixing. Nothing was imported.", [report.invalid, report.rows.length])
			: __("All {0} rows are valid.", [report.rows.length]);
	const dialog = new frappe.ui.Dialog({
		title: report.written ? __("Field wire imported") : __("Field wire import check"),
		size: "extra-large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "report",
				options: `<p>${summary}</p>
					<table class="table table-bordered table-sm">
						<thead><tr><th>${__("Row")}</th><th>${__("Item")}</th><th>${__("Item action")}</th>
						<th>${__("Spec action")}</th><th>${__("Problems")}</th></tr></thead>
						<tbody>${rows}</tbody>
					</table>`,
			},
		],
	});
	if (report.dry_run && !report.invalid) {
		dialog.set_primary_action(__("Import"), () => {
			dialog.hide();
			run_wire_import(listview, text, false);
		});
	}
	if (report.written) listview.refresh();
	dialog.show();
}
