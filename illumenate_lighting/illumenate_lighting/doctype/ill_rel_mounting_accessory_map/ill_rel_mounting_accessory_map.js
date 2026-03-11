// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Rel-Mounting-Accessory-Map", {
	refresh(frm) {
		// Set template_type default on new docs
		if (frm.is_new() && !frm.doc.template_type) {
			frm.set_value("template_type", "ilL-Fixture-Template");
		}
	},
});
