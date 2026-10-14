// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Project", {
	refresh: function (frm) {
		// Owner Company controls which dealer team sees the project: internal and sales users only
		// (mirrors portal.project_owner.can_set_owner_company).
		const can_edit_owner_company =
			frappe.session.user === "Administrator" ||
			["System Manager", "ilL Sales Review", "ilL Order Approver"].some((role) =>
				frappe.user.has_role(role)
			);
		frm.set_df_property("owner_customer", "read_only", can_edit_owner_company ? 0 : 1);
		if (!frm.is_new() && !frm.doc.owner_customer) {
			frm.set_intro(
				__("No dealer company: only the creator can see this project in the portal."),
				"orange"
			);
		} else {
			frm.set_intro("");
		}

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
	},
});
