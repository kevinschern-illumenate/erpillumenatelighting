// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.listview_settings["ilL-Webflow-Category"] = {
	add_fields: ["sync_status", "is_active"],

	onload(listview) {
		listview.page.add_inner_button(__("Targeted to Brand…"), function () {
			frappe.call({
				method: "illumenate_lighting.illumenate_lighting.api.webflow_brand.list_brands",
				args: { active_only: false },
				callback(r) {
					const brands = (r.message && r.message.brands) || [];
					if (!brands.length) {
						frappe.msgprint(__("No brands configured."));
						return;
					}
					const dlg = new frappe.ui.Dialog({
						title: __("Filter by Target Brand"),
						fields: [
							{
								fieldtype: "Select",
								fieldname: "brand",
								label: __("Brand"),
								options: brands.map(b => b.brand_code).join("\n"),
								reqd: 1,
							},
						],
						primary_action_label: __("Apply"),
						primary_action(values) {
							frappe.call({
								method: "frappe.client.get_list",
								args: {
									doctype: "ilL-Child-Webflow-Brand-Target",
									filters: {
										brand: values.brand,
										enabled: 1,
										parenttype: "ilL-Webflow-Category",
									},
									fields: ["parent"],
									limit_page_length: 0,
								},
								callback(resp) {
									const names = (resp.message || []).map(r => r.parent);
									if (!names.length) {
										frappe.msgprint(
											__("No categories targeted to {0}.", [values.brand])
										);
										return;
									}
									listview.filter_area.clear().then(() => {
										listview.filter_area.add([[
											"ilL-Webflow-Category",
											"name",
											"in",
											names,
										]]);
									});
									dlg.hide();
								},
							});
						},
					});
					dlg.show();
				},
			});
		});
	},
};
