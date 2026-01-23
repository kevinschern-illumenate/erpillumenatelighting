// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Project-Fixture-Schedule", {
	refresh(frm) {
		// Add "Convert to Sales Order" button for schedules in READY status
		// Per workflow: user sets status to READY then clicks to convert
		if (!frm.is_new() && frm.doc.status === "READY") {
			frm.add_custom_button(
				__("Convert to Sales Order"),
				function () {
					frappe.confirm(
						__(
							"This will create Items and BOMs for configured fixtures (if needed) " +
								"and generate a Sales Order. Continue?"
						),
						function () {
							frm.call({
								method: "create_sales_order",
								doc: frm.doc,
								freeze: true,
								freeze_message: __(
									"Creating Items, BOMs, and Sales Order..."
								),
								callback: function (r) {
									if (r.message) {
										frappe.set_route(
											"Form",
											"Sales Order",
											r.message
										);
									}
								},
							});
						}
					);
				},
				__("Actions")
			);
		}

		// Show warning if there are unconfigured ILLUMENATE lines
		frm.trigger("check_unconfigured_lines");
	},

	validate(frm) {
		// Prevent setting status to READY if there are unconfigured lines
		if (frm.doc.status === "READY") {
			const unconfigured = frm.trigger("get_unconfigured_lines");
			if (unconfigured && unconfigured.length > 0) {
				frappe.validated = false;
				frappe.msgprint({
					title: __("Cannot Set Status to Ready"),
					indicator: "red",
					message: __(
						"The following lines are not fully configured: {0}. " +
							"Please configure all ilLumenate fixtures before setting status to Ready.",
						[unconfigured.join(", ")]
					),
				});
			}
		}
	},

	check_unconfigured_lines(frm) {
		const unconfigured = frm.trigger("get_unconfigured_lines");
		if (unconfigured && unconfigured.length > 0) {
			frm.dashboard.add_comment(
				__(
					"<strong>Note:</strong> {0} line(s) have pending fixture configuration: {1}",
					[unconfigured.length, unconfigured.join(", ")]
				),
				"yellow",
				true
			);
		}
	},

	get_unconfigured_lines(frm) {
		const unconfigured = [];
		if (frm.doc.lines) {
			frm.doc.lines.forEach((line) => {
				if (
					line.manufacturer_type === "ILLUMENATE" &&
					!line.configured_fixture
				) {
					unconfigured.push(
						line.line_id || __("Row {0}", [line.idx])
					);
				}
			});
		}
		return unconfigured;
	},
});

// Child table events for ilL-Child-Fixture-Schedule-Line
frappe.ui.form.on("ilL-Child-Fixture-Schedule-Line", {
	manufacturer_type(frm, cdt, cdn) {
		// Clear fields when switching manufacturer type
		const row = locals[cdt][cdn];
		if (row.manufacturer_type === "OTHER") {
			frappe.model.set_value(cdt, cdn, "product_type", "");
			frappe.model.set_value(cdt, cdn, "fixture_template", "");
			frappe.model.set_value(cdt, cdn, "configured_fixture", "");
			frappe.model.set_value(cdt, cdn, "configuration_status", "");
		} else {
			frappe.model.set_value(cdt, cdn, "configuration_status", "Pending");
		}
		frm.refresh_field("lines");
	},

	product_type(frm, cdt, cdn) {
		// Clear fixture template and configured fixture when product type changes
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "fixture_template", "");
		frappe.model.set_value(cdt, cdn, "configured_fixture", "");
		if (row.manufacturer_type === "ILLUMENATE") {
			frappe.model.set_value(cdt, cdn, "configuration_status", "Pending");
		}
		frm.refresh_field("lines");
	},

	fixture_template(frm, cdt, cdn) {
		// Clear configured fixture when template changes
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "configured_fixture", "");
		if (row.manufacturer_type === "ILLUMENATE") {
			frappe.model.set_value(cdt, cdn, "configuration_status", "Pending");
		}
		frm.refresh_field("lines");
	},

	configured_fixture(frm, cdt, cdn) {
		// Update configuration status when configured fixture is set
		const row = locals[cdt][cdn];
		if (row.manufacturer_type === "ILLUMENATE") {
			if (row.configured_fixture) {
				frappe.model.set_value(cdt, cdn, "configuration_status", "Configured");
				// Fetch fixture details to populate cached fields
				frappe.db.get_value(
					"ilL-Configured-Fixture",
					row.configured_fixture,
					["manufacturable_overall_length_mm", "configured_item"],
					(r) => {
						if (r) {
							frappe.model.set_value(
								cdt,
								cdn,
								"manufacturable_length_mm",
								r.manufacturable_overall_length_mm
							);
							frappe.model.set_value(
								cdt,
								cdn,
								"ill_item_code",
								r.configured_item
							);
						}
					}
				);
			} else {
				frappe.model.set_value(cdt, cdn, "configuration_status", "Pending");
			}
		}
		frm.trigger("check_unconfigured_lines");
		frm.refresh_field("lines");
	},

	lines_add(frm, cdt, cdn) {
		// Set defaults for new rows
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "manufacturer_type", "ILLUMENATE");
		frappe.model.set_value(cdt, cdn, "configuration_status", "Pending");
	},
});
