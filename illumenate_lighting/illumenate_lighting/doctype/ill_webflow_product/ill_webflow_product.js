// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Webflow-Product", {
	refresh(frm) {
		// Add button to recalculate specifications
		if (!frm.is_new()) {
			frm.add_custom_button(__("Refresh Attribute Links"), function() {
				frm.set_value("auto_populate_attributes", 1);
				frm.save().then(() => {
					frappe.show_alert({
						message: __("Attribute links refreshed from fixture template"),
						indicator: "green"
					});
				});
			}, __("Actions"));

			// Legacy: Recalculate specs button (hidden if not using legacy specs)
			if (frm.doc.specifications && frm.doc.specifications.length > 0) {
				frm.add_custom_button(__("Recalculate Specs (Legacy)"), function() {
					frm.set_value("auto_calculate_specs", 1);
					frm.save();
				}, __("Actions"));
			}

			// Spec Sheet CSV export (Fixture Template with linked template only)
			if (frm.doc.product_type === "Fixture Template" && frm.doc.fixture_template) {
				frm.add_custom_button(__("Export Spec Sheet CSV"), function() {
					frappe.call({
						method: "illumenate_lighting.illumenate_lighting.api.spec_sheet_export.export_spec_sheet_csv",
						args: { webflow_product: frm.doc.name },
						freeze: true,
						freeze_message: __("Generating spec sheet CSV…"),
						callback(r) {
							if (r.message && r.message.success) {
								frappe.show_alert({
									message: __("CSV exported: {0}", [r.message.file_name]),
									indicator: "green"
								});
								window.open(r.message.file_url);
							} else {
								frappe.msgprint(r.message ? r.message.error : __("Export failed."));
							}
						}
					});
				}, __("Actions"));
			}
		}

		// Show sync status indicator
		if (frm.doc.sync_status === "Synced") {
			frm.dashboard.set_headline_alert(
				`<span class="indicator green">Synced to Webflow</span> - Last sync: ${frm.doc.last_synced_at || "Unknown"}`
			);
		} else if (frm.doc.sync_status === "Pending") {
			frm.dashboard.set_headline_alert(
				`<span class="indicator orange">Pending Sync</span> - Changes need to be pushed to Webflow`
			);
		} else if (frm.doc.sync_status === "Error") {
			frm.dashboard.set_headline_alert(
				`<span class="indicator red">Sync Error</span> - ${frm.doc.sync_error_message || "Unknown error"}`
			);
		}
	},

	product_type(frm) {
		// Clear source references when product type changes
		frm.set_value("fixture_template", null);
		frm.set_value("driver_spec", null);
		frm.set_value("controller_spec", null);
		frm.set_value("profile_spec", null);
		frm.set_value("lens_spec", null);
		frm.set_value("tape_spec", null);
		frm.set_value("accessory_spec", null);

		// Set appropriate category based on product type
		const category_map = {
			"Fixture Template": "linear-fixtures",
			"Driver": "drivers-power",
			"Controller": "controls",
			"Extrusion Kit": "extrusion-kits",
			"LED Tape": "components",
			"Component": "components",
			"Accessory": "components"
		};
		
		if (category_map[frm.doc.product_type]) {
			frm.set_value("product_category", category_map[frm.doc.product_type]);
		}
	},

	product_name(frm) {
		// Auto-generate slug from product name if slug is empty
		if (frm.doc.product_name && !frm.doc.product_slug) {
			const slug = frm.doc.product_name
				.toLowerCase()
				.replace(/[^a-z0-9]+/g, "-")
				.replace(/^-+|-+$/g, "");
			frm.set_value("product_slug", slug);
		}
	},

	featured_image(frm) {
		// After image upload, Frappe's File doc updates the parent's `modified`
		// timestamp via db.set_value, causing a stale-document error on save.
		// Refresh it so the next save passes the concurrency check.
		if (!frm.is_new() && frm.doc.featured_image) {
			frappe.xcall("frappe.client.get_value", {
				doctype: frm.doctype,
				filters: frm.docname,
				fieldname: "modified"
			}).then((r) => {
				if (r && r.modified) {
					frm.doc.modified = r.modified;
				}
			});
		}
	},

	fixture_template(frm) {
		// When fixture template is selected, enable configurator by default
		if (frm.doc.fixture_template) {
			frm.set_value("is_configurable", 1);
		}
	}
});

// Re-sync modified timestamp after gallery image uploads in child table
frappe.ui.form.on("ilL-Child-Webflow-Gallery-Image", {
	image(frm) {
		if (!frm.is_new()) {
			frappe.xcall("frappe.client.get_value", {
				doctype: frm.doctype,
				filters: frm.docname,
				fieldname: "modified"
			}).then((r) => {
				if (r && r.modified) {
					frm.doc.modified = r.modified;
				}
			});
		}
	}
});

// Re-sync modified timestamp after document file uploads in child table
frappe.ui.form.on("ilL-Child-Webflow-Document", {
	document_file(frm) {
		if (!frm.is_new()) {
			frappe.xcall("frappe.client.get_value", {
				doctype: frm.doctype,
				filters: frm.docname,
				fieldname: "modified"
			}).then((r) => {
				if (r && r.modified) {
					frm.doc.modified = r.modified;
				}
			});
		}
	}
});
