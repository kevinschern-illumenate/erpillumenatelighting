// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Project-Fixture-Schedule", {
	refresh(frm) {
		// Add "Convert to Sales Order" button for schedules in READY status
		// Per workflow: user sets status to READY then clicks to convert
		if (!frm.is_new() && frm.doc.status === "READY") {
			frm.add_custom_button(
				__("Convert to Sales Order"),
				function () {
					frappe.confirm(
						__(
							"This will create Items and BOMs for configured fixtures (if needed) " +
								"and generate a Sales Order. Continue?"
						),
						function () {
							frm.call({
								method: "create_sales_order",
								doc: frm.doc,
								freeze: true,
								freeze_message: __(
									"Creating Items, BOMs, and Sales Order..."
								),
								callback: function (r) {
									if (r.message) {
										frappe.set_route(
											"Form",
											"Sales Order",
											r.message
										);
									}
								},
							});
						}
					);
				},
				__("Actions")
			);
		}

		// Show warning if there are unconfigured ILLUMENATE lines
		frm.trigger("check_unconfigured_lines");
	},

	validate(frm) {
		// Prevent setting status to READY if there are unconfigured lines
		if (frm.doc.status === "READY") {
			const unconfigured = frm.trigger("get_unconfigured_lines");
			if (unconfigured && unconfigured.length > 0) {
				frappe.validated = false;
				frappe.msgprint({
					title: __("Cannot Set Status to Ready"),
					indicator: "red",
					message: __(
						"The following lines are not fully configured: {0}. " +
							"Please configure all ilLumenate fixtures before setting status to Ready.",
						[unconfigured.join(", ")]
					),
				});
			}
		}
	},

	check_unconfigured_lines(frm) {
		const unconfigured = frm.trigger("get_unconfigured_lines");
		if (unconfigured && unconfigured.length > 0) {
			frm.dashboard.add_comment(
				__(
					"<strong>Note:</strong> {0} line(s) have pending fixture configuration: {1}",
					[unconfigured.length, unconfigured.join(", ")]
				),
				"yellow",
				true
			);
		}
	},

	get_unconfigured_lines(frm) {
		const unconfigured = [];
		if (frm.doc.lines) {
			frm.doc.lines.forEach((line) => {
				if (
					line.manufacturer_type === "ILLUMENATE" &&
					!line.configured_fixture &&
					!(line.product_type === "Extrusion Kit" && line.variant_selections) &&
					!(line.product_type === "LED Tape" && line.variant_selections) &&
					!(line.product_type === "LED Neon" && line.variant_selections)
				) {
					unconfigured.push(
						line.line_id || __("Row {0}", [line.idx])
					);
				}
			});
		}
		return unconfigured;
	},
});

// Child table events for ilL-Child-Fixture-Schedule-Line
frappe.ui.form.on("ilL-Child-Fixture-Schedule-Line", {
	manufacturer_type(frm, cdt, cdn) {
		// Clear fields when switching manufacturer type
		const row = locals[cdt][cdn];
		if (row.manufacturer_type === "OTHER") {
			frappe.model.set_value(cdt, cdn, "product_type", "");
			frappe.model.set_value(cdt, cdn, "fixture_template", "");
			frappe.model.set_value(cdt, cdn, "configured_fixture", "");
			frappe.model.set_value(cdt, cdn, "configuration_status", "");
		} else {
			frappe.model.set_value(cdt, cdn, "configuration_status", "Pending");
		}
		frm.refresh_field("lines");
	},

	product_type(frm, cdt, cdn) {
		// Clear fixture template, kit template, and configured fixture when product type changes
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "fixture_template", "");
		frappe.model.set_value(cdt, cdn, "kit_template", "");
		frappe.model.set_value(cdt, cdn, "configured_fixture", "");
		frappe.model.set_value(cdt, cdn, "variant_selections", "");
		if (row.manufacturer_type === "ILLUMENATE") {
			frappe.model.set_value(cdt, cdn, "configuration_status", "Pending");
		}
		frm.refresh_field("lines");
	},

	fixture_template(frm, cdt, cdn) {
		// Clear configured fixture when template changes
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "configured_fixture", "");
		if (row.manufacturer_type === "ILLUMENATE") {
			frappe.model.set_value(cdt, cdn, "configuration_status", "Pending");
		}
		frm.refresh_field("lines");
	},

	configured_fixture(frm, cdt, cdn) {
		// Update configuration status when configured fixture is set
		const row = locals[cdt][cdn];
		if (row.manufacturer_type === "ILLUMENATE") {
			if (row.configured_fixture) {
				frappe.model.set_value(cdt, cdn, "configuration_status", "Configured");
				// Fetch fixture details to populate cached fields
				frappe.db.get_value(
					"ilL-Configured-Fixture",
					row.configured_fixture,
					["manufacturable_overall_length_mm", "configured_item"],
					(r) => {
						if (r) {
							frappe.model.set_value(
								cdt,
								cdn,
								"manufacturable_length_mm",
								r.manufacturable_overall_length_mm
							);
							frappe.model.set_value(
								cdt,
								cdn,
								"ill_item_code",
								r.configured_item
							);
						}
					}
				);
			} else {
				frappe.model.set_value(cdt, cdn, "configuration_status", "Pending");
			}
		}
		frm.trigger("check_unconfigured_lines");
		frm.refresh_field("lines");
	},

	lines_add(frm, cdt, cdn) {
		// Set defaults for new rows
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "manufacturer_type", "ILLUMENATE");
		frappe.model.set_value(cdt, cdn, "configuration_status", "Pending");
	},

	kit_template(frm, cdt, cdn) {
		// When kit template is selected, reset configuration and offer Configure button
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "variant_selections", "");
		frappe.model.set_value(cdt, cdn, "ill_item_code", "");
		frappe.model.set_value(cdt, cdn, "configuration_status", "Pending");
		frm.refresh_field("lines");

		if (row.kit_template && row.product_type === "Extrusion Kit") {
			// Open the kit configurator dialog
			ill_open_kit_configurator(frm, cdt, cdn, row.kit_template);
		}
	},
});


// ═══════════════════════════════════════════════════════════════════════
// EXTRUSION KIT CONFIGURATOR DIALOG
// ═══════════════════════════════════════════════════════════════════════

/**
 * Opens a dialog for configuring an Extrusion Kit.
 * Loads options from the kit template, presents cascading dropdowns,
 * validates the configuration, and saves to the schedule line.
 */
function ill_open_kit_configurator(frm, cdt, cdn, kit_template_name) {
	// Fetch configurator init data
	frappe.call({
		method: "illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator.get_kit_configurator_init",
		args: { kit_template_name: kit_template_name },
		freeze: true,
		freeze_message: __("Loading kit options..."),
		callback: function (r) {
			if (!r.message || !r.message.success) {
				frappe.msgprint({
					title: __("Error"),
					indicator: "red",
					message: r.message ? r.message.error : __("Failed to load kit options"),
				});
				return;
			}

			const init_data = r.message;
			_show_kit_configurator_dialog(frm, cdt, cdn, init_data);
		},
	});
}

/**
 * Shows the multi-step configurator dialog with all attribute selectors.
 */
function _show_kit_configurator_dialog(frm, cdt, cdn, init_data) {
	const kit = init_data.kit_template;
	const options = init_data.options;
	const defaults = init_data.defaults || {};

	// Build select options for each attribute
	const make_options = (opt_list) => {
		return [""].concat((opt_list || []).map((o) => o.value));
	};

	const d = new frappe.ui.Dialog({
		title: __("Configure Extrusion Kit: {0}", [kit.template_name]),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				fields_html: `
					<div class="alert alert-info" style="margin-bottom: 15px;">
						<strong>${__("Kit Contents")}:</strong>
						${kit.profile_stock_length_mm}mm Profile •
						${kit.lens_stock_length_mm}mm Lens •
						${kit.mounting_accessory_qty} Mounting Clips •
						${kit.solid_endcap_qty} Solid Endcaps •
						${kit.feed_through_endcap_qty} Feed-Through Endcaps
					</div>
				`,
			},
			{
				fieldtype: "Section Break",
				label: __("Select Attributes"),
			},
			{
				fieldname: "finish",
				fieldtype: "Select",
				label: __("Finish"),
				options: make_options(options.finish),
				default: defaults.finish || "",
				reqd: 1,
			},
			{
				fieldname: "lens_appearance",
				fieldtype: "Select",
				label: __("Lens Appearance"),
				options: make_options(options.lens_appearance),
				default: defaults.lens_appearance || "",
				reqd: 1,
			},
			{
				fieldtype: "Column Break",
			},
			{
				fieldname: "mounting_method",
				fieldtype: "Select",
				label: __("Mounting Method"),
				options: make_options(options.mounting_method),
				default: defaults.mounting_method || "",
				reqd: 1,
			},
			{
				fieldname: "endcap_style",
				fieldtype: "Select",
				label: __("Endcap Style"),
				options: make_options(options.endcap_style),
				default: defaults.endcap_style || "",
				reqd: 1,
			},
			{
				fieldname: "endcap_color",
				fieldtype: "Select",
				label: __("Endcap Color"),
				options: make_options(options.endcap_color),
				default: defaults.endcap_color || "",
				reqd: 1,
			},
			{
				fieldtype: "Section Break",
				label: __("Resolved Components"),
			},
			{
				fieldname: "resolved_info",
				fieldtype: "HTML",
				label: __("Component Details"),
			},
		],
		primary_action_label: __("Configure & Add to Schedule"),
		primary_action: function () {
			const values = d.get_values();
			if (!values) return;

			values.kit_template = kit.name;

			// Validate and resolve via the API
			frappe.call({
				method: "illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator.validate_kit_configuration",
				args: { selections: JSON.stringify(values) },
				freeze: true,
				freeze_message: __("Validating configuration..."),
				callback: function (r) {
					if (!r.message || !r.message.is_valid) {
						frappe.msgprint({
							title: __("Validation Error"),
							indicator: "red",
							message: r.message ? r.message.error : __("Configuration invalid"),
						});
						return;
					}

					const result = r.message;

					// Save to schedule line
					const row = locals[cdt][cdn];
					frappe.model.set_value(cdt, cdn, "ill_item_code", result.part_number);
					frappe.model.set_value(cdt, cdn, "notes", result.build_description);
					frappe.model.set_value(cdt, cdn, "configuration_status", "Configured");
					frappe.model.set_value(
						cdt, cdn, "variant_selections",
						JSON.stringify({
							product_category: "Extrusion Kit",
							part_number: result.part_number,
							build_description: result.build_description,
							kit_composition: result.kit_composition,
							spec_data: result.spec_data,
							resolved_items: result.resolved_items,
							selections: result.selections,
							kit_template: result.kit_template,
						})
					);

					frm.dirty();
					frm.refresh_field("lines");

					d.hide();
					frappe.show_alert({
						message: __(
							"Extrusion Kit configured: {0}",
							[result.part_number]
						),
						indicator: "green",
					});
				},
			});
		},
	});

	// ── Cascading logic: update available options on selection change ──
	const cascade_fields = ["finish", "endcap_style", "mounting_method"];
	cascade_fields.forEach((field) => {
		d.fields_dict[field].df.onchange = function () {
			const vals = d.get_values(true);
			_refresh_kit_cascading(d, kit.name, vals);
		};
	});

	// ── Preview: update resolved components on any change ──
	const all_fields = ["finish", "lens_appearance", "mounting_method", "endcap_style", "endcap_color"];
	all_fields.forEach((field) => {
		const existing_onchange = d.fields_dict[field].df.onchange;
		d.fields_dict[field].df.onchange = function () {
			if (existing_onchange) existing_onchange();
			_update_kit_preview(d, kit);
		};
	});

	d.show();
}

/**
 * Refresh cascading options (filter dropdowns based on prior selections).
 */
function _refresh_kit_cascading(dialog, kit_template_name, current_values) {
	frappe.call({
		method: "illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator.get_kit_cascading_options",
		args: {
			kit_template_name: kit_template_name,
			finish: current_values.finish || null,
			lens_appearance: current_values.lens_appearance || null,
			mounting_method: current_values.mounting_method || null,
			endcap_style: current_values.endcap_style || null,
		},
		async: true,
		callback: function (r) {
			if (!r.message || !r.message.success) return;
			const data = r.message;

			// Update available endcap colors if endcap_style was changed
			if (data.available_endcap_colors) {
				const endcap_color_field = dialog.fields_dict.endcap_color;
				const color_options = [""].concat(
					data.available_endcap_colors.map((c) => c.value)
				);
				endcap_color_field.df.options = color_options;
				endcap_color_field.refresh();

				// Reset color if current selection is not in new options
				const current_color = dialog.get_value("endcap_color");
				if (current_color && !color_options.includes(current_color)) {
					dialog.set_value("endcap_color", "");
				}
			}

			// Update lens appearances if finish was changed
			if (data.available_lens_appearances) {
				const lens_field = dialog.fields_dict.lens_appearance;
				const lens_options = [""].concat(
					data.available_lens_appearances.map((l) => l.value)
				);
				lens_field.df.options = lens_options;
				lens_field.refresh();

				const current_lens = dialog.get_value("lens_appearance");
				if (current_lens && !lens_options.includes(current_lens)) {
					dialog.set_value("lens_appearance", "");
				}
			}

			// Show profile/mounting availability indicators
			if (data.profile_available === false) {
				frappe.show_alert({
					message: __("No profile found for this finish. Check Kit Profile Maps."),
					indicator: "orange",
				});
			}
			if (data.mounting_available === false) {
				frappe.show_alert({
					message: __("No mounting accessory for this method. Check Kit Mounting Maps."),
					indicator: "orange",
				});
			}
		},
	});
}

/**
 * Update the preview HTML showing what components will be resolved.
 */
function _update_kit_preview(dialog, kit) {
	const vals = dialog.get_values(true);
	const has_all = vals.finish && vals.lens_appearance && vals.mounting_method &&
		vals.endcap_style && vals.endcap_color;

	let html = "";
	if (!has_all) {
		html = `<p class="text-muted">${__("Complete all selections above to see resolved components.")}</p>`;
	} else {
		html = `
			<div class="alert alert-success">
				<strong>${__("Kit Configuration Summary")}</strong><br>
				<table class="table table-condensed" style="margin-top: 8px; margin-bottom: 0;">
					<tr><td><strong>${__("Finish")}</strong></td><td>${vals.finish}</td></tr>
					<tr><td><strong>${__("Lens")}</strong></td><td>${vals.lens_appearance}</td></tr>
					<tr><td><strong>${__("Mounting")}</strong></td><td>${vals.mounting_method}</td></tr>
					<tr><td><strong>${__("Endcap Style")}</strong></td><td>${vals.endcap_style}</td></tr>
					<tr><td><strong>${__("Endcap Color")}</strong></td><td>${vals.endcap_color}</td></tr>
					<tr><td colspan="2"><hr style="margin:4px 0;"></td></tr>
					<tr><td>${__("Profile")}</td><td>${kit.profile_stock_length_mm}mm ×1</td></tr>
					<tr><td>${__("Lens")}</td><td>${kit.lens_stock_length_mm}mm ×1</td></tr>
					<tr><td>${__("Mounting Clips")}</td><td>×${kit.mounting_accessory_qty}</td></tr>
					<tr><td>${__("Solid Endcaps")}</td><td>×${kit.solid_endcap_qty}</td></tr>
					<tr><td>${__("Feed-Through Endcaps")}</td><td>×${kit.feed_through_endcap_qty}</td></tr>
				</table>
				<p class="text-muted" style="margin-bottom: 0; margin-top: 8px;">
					${__("Click 'Configure & Add to Schedule' to validate and resolve all component Items.")}
				</p>
			</div>
		`;
	}

	dialog.fields_dict.resolved_info.$wrapper.html(html);
}