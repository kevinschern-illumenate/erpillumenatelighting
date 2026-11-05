// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Webflow-Product", {
	refresh(frm) {
		if (is_duplicate_doc(frm)) {
			clear_only_webflow_sync_section(frm);
		}

		if (!frm.is_new()) {
			let sync_btn = frm.add_custom_button(__('Sync to Webflow'), function() {
				
				// --- STEP 2 FIX: Darken the background overlay temporarily ---
				if (!$('#custom-freeze-style').length) {
					$('<style id="custom-freeze-style">.freeze { background-color: rgba(0, 0, 0, 0.75) !important; backdrop-filter: blur(3px); }</style>').appendTo('head');
				}

				// --- STEP 1 & 2 FIX: Single message, styled as a solid, readable card ---
				const freezeMsg = `
					<div style="background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); max-width: 450px; margin: 0 auto; color: #172e48; border: 2px solid #fdc757; text-align: center;">
						<h4 style="margin-top: 0; margin-bottom: 15px; color: #172e48; font-weight: 700;">Syncing to Webflow</h4>
						<p style="margin-bottom: 0; font-size: 15px; font-weight: 500; line-height: 1.5;">Please wait, this might take a few minutes. The page will unfreeze once the spec sheet has been successfully generated and Webflow has been updated.</p>
					</div>
				`;
				frappe.dom.freeze(freezeMsg);
				const api = 'illumenate_lighting.illumenate_lighting.api.webflow_export_v2.';
				const controller = new AbortController();
				let checkInterval;
				let finished = false;
				const finish = () => {
					finished = true;
					clearInterval(checkInterval);
					clearTimeout(deadline);
					frappe.dom.unfreeze();
					$('#custom-freeze-style').remove();
				};
				const fail = (title, message) => {
					if (finished) return;
					finish();
					frappe.msgprint({ title, message: message || __('An error occurred.'), indicator: 'red' });
				};
				// Start the deadline before the request: the pipeline may never respond.
				const deadline = setTimeout(() => {
					finish();
					controller.abort();
					frappe.msgprint(__('Sync has not been confirmed. It may still be running in the background.'));
					frm.reload_doc();
				}, 120000);

				// The server baseline time makes sure an earlier "Synced" is not mistaken
				// for this run. Every enabled target brand is requested.
				frappe.xcall(api + 'get_sync_progress', { docname: frm.doc.name }).then(baseline => {
					const since = baseline && baseline.server_time;
					const brands = ((baseline && baseline.brands) || []).map(row => row.brand);
					return Promise.all((brands.length ? brands : [null]).map(brand =>
						frappe.xcall(api + 'request_spec_sheet', brand ? { docname: frm.doc.name, brand } : { docname: frm.doc.name })
					)).then(responses => {
						// The deadline may already have released the form; do not start polling then.
						if (finished) return since;
						if (responses.some(response => !response)) throw new Error(__('No response from server.'));
						return since;
					});
				}).then(since => {
					// The deadline may already have released the form; do not start polling then.
					if (finished) return;
					checkInterval = setInterval(() => {
						frappe.xcall(api + 'get_sync_progress', { docname: frm.doc.name, since }).then(progress => {
							if (finished || !progress) return;
							if (progress.failed) {
								const errors = (progress.brands || [])
									.filter(row => row.state === 'failed')
									.map(row => `${row.brand}: ${row.error || __('failed')}`);
								fail(__('Sync Error'), frappe.utils.escape_html(errors.join('; ')) || __('Pipeline failed. Check logs.'));
								frm.reload_doc();
							} else if (progress.complete) {
								finish();
								const superseded = (progress.brands || []).some(row => row.state === 'superseded');
								frappe.show_alert({
									message: superseded
										? __('Webflow sync finished for an older revision. Sync again to publish the latest changes.')
										: __('Webflow Sync Complete!'),
									indicator: superseded ? 'orange' : 'green'
								});
								frm.reload_doc();
							}
						}).catch(err => console.error("Polling error:", err));
					}, 3000);
				}).catch(err => fail(__('Sync Failed'), err && err.message && frappe.utils.escape_html(String(err.message))));
			});

			sync_btn.css({
				'background-color': '#fdc757',
				'color': '#172e48',
				'font-weight': 'bold',
				'border-color': '#fdc757'
			});

			// Display Target Brands in the Sidebar
		if (frm.doc.target_brands && frm.doc.target_brands.length > 0) {
			let active_brands = frm.doc.target_brands
				.filter(row => row.enabled)
				.map(row => {
					// Map backend codes to pretty names
					if (row.brand === "lighting_206") return "206 Lighting";
					if (row.brand === "illumenate") return "ilLumenate Lighting";
					return row.brand;
				});

			if (active_brands.length > 0) {
				let brand_html = `
					<div style="margin-top: 10px; margin-bottom: -10px; padding: 0 15px;">
						<div>
				`;
				
				active_brands.forEach(brand => {
					let color = brand === "206 Lighting" ? "#fdc757" : "#0052cc";
					let text_color = brand === "206 Lighting" ? "#172e48" : "white";
					brand_html += `<span class="badge" style="background-color: ${color}; color: ${text_color}; margin-right: 5px; font-weight: 500;">${brand}</span>`;
				});
				
				brand_html += `</div></div>`;
				
				// Inject into the top of the sidebar
				$('.layout-side-section').prepend(brand_html);
			}
		}
			
			// Direct link to open live product on Webflow site (Dynamic by Brand)
			const slug = frm.doc.product_slug || frm.doc.name;
			
			if (slug && frm.doc.target_brands && frm.doc.target_brands.length > 0) {
				let active_brands = frm.doc.target_brands.filter(row => row.enabled);
				
				if (active_brands.length === 1) {
					// Single brand -> Standard button
					let brandCode = active_brands[0].brand;
					let domain = brandCode === "lighting_206" ? "https://206.lighting" : "https://illumenate.lighting";
					
					frm.add_custom_button(__("Open in Webflow"), function() {
						window.open(`${domain}/products/${slug}`, "_blank");
					});
				} else if (active_brands.length > 1) {
					// Multiple brands -> Dropdown menu!
					active_brands.forEach(row => {
						let brandCode = row.brand;
						let brandName = brandCode === "lighting_206" ? "206 Lighting" : "ilLumenate Lighting";
						let domain = brandCode === "lighting_206" ? "https://206.lighting" : "https://illumenate.lighting";
						
						frm.add_custom_button(__(`View on ${brandName}`), function() {
							window.open(`${domain}/products/${slug}`, "_blank");
						}, __("Open in Webflow")); 
					});
				}
			} else if (slug) {
				// Safety fallback if no brands are set
				frm.add_custom_button(__("Open in Webflow"), function() {
					window.open(`https://illumenate.lighting/products/${slug}`, "_blank");
				});
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

		show_staging_webflow_banner(frm);

		// Limit Compatible Products to products matching this document's active brands
		frm.set_query("related_product", "compatible_products", function(doc, cdt, cdn) {
			let active_brands = [];
			if (doc.target_brands && doc.target_brands.length > 0) {
				active_brands = doc.target_brands.filter(b => b.enabled).map(b => b.brand);
			} else {
				active_brands = ["lighting_206"]; // Fallback 
			}

			return {
				query: "illumenate_lighting.illumenate_lighting.api.webflow_brand.get_brand_filtered_products",
				filters: {
					"brands": active_brands
				}
			};
		});
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
		.get_value(TEMPLATE_LINKS[fieldname], frm.doc[fieldname], ["series"])
		.then((r) => {
			// Product Category, Product Type and Series follow the template on save.
			const template = (r && r.message) || {};
			if (template.series) {
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

// Plan 4.11 item 6: on a staging site, Webflow writes go to "[staging]" items
// only. The environment comes from site config and is fetched once per page load.
let webflow_environment_promise = null;
function show_staging_webflow_banner(frm) {
	if (!webflow_environment_promise) {
		webflow_environment_promise = frappe
			.xcall("illumenate_lighting.illumenate_lighting.api.n8n_config.get_webflow_environment")
			.catch(() => null);
	}
	webflow_environment_promise.then((environment) => {
		if (environment === "staging") {
			frm.set_intro(
				__("Staging: Webflow writes go to [staging] items only. They are always hidden from the public."),
				"orange"
			);
		}
	});
}

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
