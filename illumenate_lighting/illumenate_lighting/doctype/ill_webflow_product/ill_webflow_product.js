// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Webflow-Product", {
	refresh(frm) {
		if (is_duplicate_doc(frm)) {
			clear_only_webflow_sync_section(frm);
		}

		if (!frm.is_new()) {
			let sync_btn = frm.add_custom_button(__('Sync to Webflow'), function() {
				
				// STEP 1: Freeze for PDF Generation
				frappe.dom.freeze(__('Step 1/2: Generating Spec Sheets & Attaching Files...'));

				fetch('https://illumenatelighting.app.n8n.cloud/webhook/generate-spec-sheet-v2', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({
						product: frm.doc.name,
						product_slug: frm.doc.product_slug || frm.doc.name,
						brand: 'lighting_206'
					})
				})
				.then(response => {
					if (!response.ok) throw new Error(`Pipeline failed with status ${response.status}.`);
					return response.json();
				})
				.then(data => {
                    if (data.success === false) {
                        throw new Error(data.message || "Pipeline reported an issue.");
                    }

					// STEP 2: PDFs are done. Start checking the database for Workflow 2's finish!
					frappe.dom.freeze(__('Step 2/2: Spec sheets saved. Pushing to Webflow...'));

					let checkInterval = setInterval(() => {
						// Use xcall to bypass the browser cache!
						frappe.xcall('frappe.client.get_value', {
							doctype: 'ilL-Webflow-Product',
							filters: { name: frm.doc.name },
							fieldname: 'sync_status'
						}).then(r => {
							if (!r) return;
							let current_status = r.sync_status;
							
							if (current_status === 'Synced' || current_status === 'LIVE') {
								clearInterval(checkInterval);
								frappe.dom.unfreeze();
								frappe.show_alert({message: __('Webflow Sync Complete!'), indicator: 'green'});
								frm.reload_doc();
							} 
							else if (current_status === 'Error' || current_status === 'Failed') {
								clearInterval(checkInterval);
								frappe.dom.unfreeze();
								frappe.msgprint({title: __('Sync Error'), message: __('Pipeline failed. Check logs.'), indicator: 'red'});
								frm.reload_doc();
							}
						}).catch(err => console.error("Polling error:", err));
					}, 3000);

					// Safety timeout after 2 minutes
					setTimeout(() => {
						clearInterval(checkInterval);
						if (document.querySelector('.freeze-message-container')) { 
							frappe.dom.unfreeze();
							frappe.msgprint(__('Sync is taking longer than usual. It is running in the background.'));
							frm.reload_doc();
						}
					}, 120000);

				})
				.catch(err => {
					frappe.dom.unfreeze();
					frappe.msgprint({title: __('Sync Failed'), message: err.message, indicator: 'red'});
				});
			});

			sync_btn.css({
				'background-color': '#fdc757',
				'color': '#172e48',
				'font-weight': 'bold',
				'border-color': '#fdc757'
			});
			
			// Direct link to open live product on Webflow site
			frm.add_custom_button(__("Open in Webflow"), function() {
				const slug = frm.doc.product_slug || frm.doc.name;
				if (!slug) {
					frappe.msgprint(__("No product slug found for this product."));
					return;
				}
				window.open(`https://illumenate.lighting/products/${slug}`, "_blank");
			});

			// Add button to recalculate specifications
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
				|| (["LED Tape", "COB Tape", "LED Neon"].includes(frm.doc.product_type) && frm.doc.tape_neon_template)
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

	before_save(frm) {
		// Hard safety net: clear fields again right before saving a duplicate
		if (is_duplicate_doc(frm)) {
			clear_only_webflow_sync_section(frm);
		}
	},

	product_type(frm) {
		// Clear source references when product type changes
		[...Object.keys(TEMPLATE_LINKS), ...SPEC_LINKS].forEach((fieldname) => {
			if (frm.doc[fieldname]) {
				frm.set_value(fieldname, null);
			}
		});

		// Set appropriate category based on product type
		const category_map = {
			"Fixture Template": "linear-fixtures",
			"Driver": "drivers-power",
			"Controller": "controls",
			"Extrusion Kit": "extrusion-kits",
			"LED Tape": "components",
			"COB Tape": "components",
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
		on_template_change(frm, "fixture_template");
	},
	tape_neon_template(frm) {
		on_template_change(frm, "tape_neon_template");
	},
	led_sheet_template(frm) {
		on_template_change(frm, "led_sheet_template");
	},
	kit_template(frm) {
		on_template_change(frm, "kit_template");
	},
	driver_template(frm) {
		on_template_change(frm, "driver_template");
	},
	controller_template(frm) {
		on_template_change(frm, "controller_template");
	},
});

// Template link field -> template doctype. Mirrors WEBFLOW_PRODUCT_LINKS in
// web_listing_schema.py; each one is shown only for its product type.
const TEMPLATE_LINKS = {
	fixture_template: "ilL-Fixture-Template",
	tape_neon_template: "ilL-Tape-Neon-Template",
	led_sheet_template: "ilL-LED-Sheet-Template",
	kit_template: "ilL-Extrusion-Kit-Template",
	driver_template: "ilL-Driver-Template",
	controller_template: "ilL-Controller-Template",
};

const SPEC_LINKS = [
	"driver_spec",
	"controller_spec",
	"profile_spec",
	"lens_spec",
	"tape_spec",
	"accessory_spec",
];

function on_template_change(frm, fieldname) {
	// A template drives the configurator, so enable it, and carry the
	// template's category and series onto the product when it has them.
	if (!frm.doc[fieldname]) {
		return;
	}
	frm.set_value("is_configurable", 1);
	frappe.db
		.get_value(TEMPLATE_LINKS[fieldname], frm.doc[fieldname], ["product_category", "series"])
		.then((r) => {
			const template = (r && r.message) || {};
			if (template.product_category) {
				frm.set_value("product_category", template.product_category);
			}
			if (template.series && !frm.doc.series) {
				frm.set_value("series", template.series);
			}
		});
}

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

function is_duplicate_doc(frm) {
	// Frappe duplicate creates a new unsaved doc with copied values
	return frm.is_new() && !!frm.doc.__islocal && !!frm.doc.amended_from === false;
}

function clear_only_webflow_sync_section(frm) {
	// Parent sync fields only
	frm.set_value("webflow_item_id", null);
	frm.set_value("webflow_collection_slug", null);
	frm.set_value("last_synced_at", null);
	frm.set_value("sync_error_message", null);
	frm.set_value("sync_status", "Never Synced");

	// Only clear Sync Targets (per-brand webflow IDs)
	frm.set_value("sync_targets", []);

	// KEEP target_brands and all other product data untouched
	frm.refresh_fields([
		"webflow_item_id",
		"webflow_collection_slug",
		"last_synced_at",
		"sync_error_message",
		"sync_status",
		"sync_targets"
	]);
}
