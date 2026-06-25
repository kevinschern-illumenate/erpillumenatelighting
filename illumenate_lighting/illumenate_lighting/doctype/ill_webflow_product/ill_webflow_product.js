// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Webflow-Product", {
	refresh(frm) {
		// If opened as a duplicated doc, clear sync sections immediately
		if (frm.is_new() && frm.doc.__islocal) {
			force_clear_webflow_brand_sync(frm);
		}

		// Override Duplicate menu action explicitly
		frm.page.clear_menu();
		frm.page.add_menu_item(__("Duplicate"), () => {
			frappe.model.copy_doc(frm.doc);
			frappe.set_route("Form", frm.doctype, frappe.model.get_new_name(frm.doctype));
		});

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

			// Spec Sheet CSV export (Fixture Template with linked template,
			// or LED Tape/Neon with linked tape_neon_template)
			if (
				(frm.doc.product_type === "Fixture Template" && frm.doc.fixture_template)
				|| (["LED Tape", "LED Neon"].includes(frm.doc.product_type) && frm.doc.tape_neon_template)
			) {
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

			// Per-brand "Sync Now" — flips sync_status=Pending on the chosen
			// target_brand rows so n8n picks the product up on next run.
			frm.add_custom_button(__("Sync Now (Per Brand)"), function() {
				const targeted = (frm.doc.target_brands || [])
					.filter(r => r.enabled)
					.map(r => r.brand);
				if (targeted.length === 0) {
					frappe.msgprint(__("No target brands set on this product."));
					return;
				}
				const dlg = new frappe.ui.Dialog({
					title: __("Mark Product Pending Sync"),
					fields: [
						{
							fieldtype: "MultiCheck",
							fieldname: "brands",
							label: __("Target Brands"),
							options: targeted.map(b => ({ label: b, value: b, checked: 1 })),
						},
					],
					primary_action_label: __("Mark Pending"),
					primary_action(values) {
						const selected = (values.brands || []);
						if (!selected.length) {
							frappe.msgprint(__("Pick at least one brand."));
							return;
						}
						const calls = selected.map(brand => frappe.call({
							method: "illumenate_lighting.illumenate_lighting.api.webflow_export.trigger_sync",
							args: { product_slugs: [frm.doc.name], brand: brand },
						}));
						Promise.all(calls).then(() => {
							frappe.show_alert({
								message: __("Marked pending for: {0}", [selected.join(", ")]),
								indicator: "green",
							});
							dlg.hide();
							frm.reload_doc();
						});
					},
				});
				dlg.show();
			}, __("Actions"));

			// Per-brand Webflow CMS deep links built from sync_targets.
			(frm.doc.sync_targets || []).forEach((row) => {
				if (!row.webflow_item_id) return;
				const label = __("Open in Webflow ({0})", [row.brand]);
				frm.add_custom_button(label, function() {
					frappe.call({
						method: "illumenate_lighting.illumenate_lighting.api.webflow_brand.get_brand_config",
						args: { brand: row.brand },
						callback(r) {
							const cfg = r.message || {};
							const site = cfg.webflow_site_url || "";
							if (!site) {
								frappe.msgprint(__("No Webflow site URL configured for brand {0}.", [row.brand]));
								return;
							}
							window.open(site, "_blank");
						},
					});
				}, __("Open in Webflow"));
			});
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

	onload_post_render(frm) {
		// Second-pass clear after grid rendering
		if (frm.is_new() && frm.doc.__islocal) {
			force_clear_webflow_brand_sync(frm);
			frm.refresh_fields(["sync_targets", "target_brands", "webflow_item_id", "sync_status"]);
		}
	},

	before_save(frm) {
		// Hard safety before save
		if (frm.is_new()) {
			force_clear_webflow_brand_sync(frm);
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
		frm.set_value("tape_neon_template", null);
		frm.set_value("accessory_spec", null);

		// Set appropriate category based on product type
		const category_map = {
			"Fixture Template": "linear-fixtures",
			"Driver": "drivers-power",
			"Controller": "controls",
			"Extrusion Kit": "extrusion-kits",
			"LED Tape": "components",
			"LED Neon": "components",
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

	dimensions_image(frm) {
		// After image upload, Frappe's File doc updates the parent's `modified`
		// timestamp via db.set_value, causing a stale-document error on save.
		// Refresh it so the next save passes the concurrency check.
		if (!frm.is_new() && frm.doc.dimensions_image) {
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

	series_family_image(frm) {
		// After image upload, Frappe's File doc updates the parent's `modified`
		// timestamp via db.set_value, causing a stale-document error on save.
		// Refresh it so the next save passes the concurrency check.
		if (!frm.is_new() && frm.doc.series_family_image) {
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
	},

	tape_neon_template(frm) {
		// When tape/neon template is selected, enable configurator by default
		if (frm.doc.tape_neon_template) {
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

function force_clear_webflow_brand_sync(frm) {
	// Parent sync fields
	frm.set_value("webflow_item_id", "");
	frm.set_value("webflow_collection_slug", "");
	frm.set_value("last_synced_at", null);
	frm.set_value("sync_error_message", "");
	frm.set_value("sync_status", "Never Synced");

	// Child tables in Webflow Brands & Sync section
	frm.set_value("sync_targets", []);
	// Keep or clear target brands depending on your preference:
	// frm.set_value("target_brands", []);

	// Direct doc-level wipe in case grid model already holds rows
	frm.doc.sync_targets = [];
	if (frm.doc.webflow_item_id) frm.doc.webflow_item_id = "";
}
