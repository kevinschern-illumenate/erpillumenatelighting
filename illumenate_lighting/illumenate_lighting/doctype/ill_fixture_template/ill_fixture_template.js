// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Fixture-Template", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Populate Part Number Builder"), function () {
				frappe.call({
					method:
						"illumenate_lighting.illumenate_lighting.doctype.ill_fixture_template.ill_fixture_template.populate_part_number_builder",
					args: { docname: frm.doc.name },
					freeze: true,
					freeze_message: __("Populating Part Number Builder…"),
					callback: function (r) {
						if (r.message) {
							frm.reload_doc();
							frappe.show_alert({
								message: __("Part Number Builder populated."),
								indicator: "green",
							});
						}
					},
				});
			});
		}
	},
});
