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
	},
});
