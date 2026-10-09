// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Spec-Wire", {
	setup(frm) {
		frm.set_query("item", () => ({ filters: { is_sales_item: 1, disabled: 0, has_variants: 0 } }));
	},
});
