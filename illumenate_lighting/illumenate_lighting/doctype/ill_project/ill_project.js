// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Project", {
	refresh: function (frm) {
		// Add button to create a new schedule
		if (!frm.is_new()) {
			frm.add_custom_button(
				__("Create Schedule"),
				function () {
					frappe.new_doc("ilL-Project-Fixture-Schedule", {
						ill_project: frm.doc.name,
						customer: frm.doc.customer,
					});
				},
				__("Actions")
			);
		}

		// Show collaborators section only if private
		frm.toggle_display("collaborators", frm.doc.is_private);
	},

	is_private: function (frm) {
		// Toggle collaborators section visibility
		frm.toggle_display("collaborators", frm.doc.is_private);
	},
});
