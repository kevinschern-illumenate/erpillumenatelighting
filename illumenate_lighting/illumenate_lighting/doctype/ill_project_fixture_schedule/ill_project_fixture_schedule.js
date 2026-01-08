// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Project-Fixture-Schedule", {
	refresh(frm) {
		// Add "Create Sales Order" button for saved documents that are not yet ORDERED
		if (!frm.is_new() && frm.doc.status !== "ORDERED" && frm.doc.status !== "CLOSED") {
			frm.add_custom_button(
				__("Create Sales Order"),
				function () {
					frm.call({
						method: "create_sales_order",
						doc: frm.doc,
						freeze: true,
						freeze_message: __("Creating Sales Order..."),
						callback: function (r) {
							if (r.message) {
								frappe.set_route("Form", "Sales Order", r.message);
							}
						},
					});
				},
				__("Actions")
			);
		}
	},
});
