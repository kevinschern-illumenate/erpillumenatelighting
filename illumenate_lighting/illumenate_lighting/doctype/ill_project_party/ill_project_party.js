// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

// DESK-9: a party becomes a Customer only when Sales quotes or bills it directly.
frappe.ui.form.on("ilL-Project-Party", {
	refresh(frm) {
		const is_sales =
			frappe.session.user === "Administrator" ||
			["System Manager", "ilL Sales Review", "ilL Order Approver"].some((role) => frappe.user.has_role(role));
		if (frm.is_new() || !is_sales) return;
		frm.add_custom_button(frm.doc.customer ? __("Link to another Customer") : __("Promote to Customer"), () => {
			const dialog = new frappe.ui.Dialog({
				title: __("Promote to Customer"),
				fields: [
					{
						fieldname: "customer",
						fieldtype: "Link",
						options: "Customer",
						label: __("Existing Customer"),
						description: __("Leave empty to create a Customer named {0}.", [frm.doc.party_name]),
					},
				],
				primary_action_label: __("Promote"),
				primary_action(values) {
					frappe
						.call({
							method: "illumenate_lighting.illumenate_lighting.portal.project_parties.promote_to_customer",
							type: "POST",
							args: { party: frm.doc.name, customer: values.customer || null },
							freeze: true,
						})
						.then((r) => {
							dialog.hide();
							const result = r.message || {};
							frappe.show_alert({
								message: __("Linked to Customer {0}; {1} project(s) now bill it.", [
									result.customer,
									(result.projects || []).length,
								]),
								indicator: "green",
							});
							frm.reload_doc();
						});
				},
			});
			dialog.show();
		});
	},
});
