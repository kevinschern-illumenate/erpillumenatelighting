// ilLumenate Lighting - Sales Order customizations
// Adds button to generate manufacturing artifacts from configured fixtures
// Adds "Section / Room" grouping support (parity with Quotation)

function with_quote_order_configurator(callback) {
	const configurator = window.illumenate_lighting && window.illumenate_lighting.quote_order_configurator;
	if (configurator) {
		callback(configurator);
		return;
	}

	frappe.require('/assets/illumenate_lighting/js/quote_order_configurator.js', function() {
		callback(window.illumenate_lighting.quote_order_configurator);
	});
}

function is_sales_order_read_only(frm) {
	if (typeof frm.is_read_only === 'function') {
		return frm.is_read_only();
	}

	return !!frm.read_only || (frm.doc && frm.doc.docstatus !== 0);
}

frappe.ui.form.on('Sales Order', {
	refresh: function(frm) {
		with_quote_order_configurator(function(configurator) {
			configurator.add_buttons(frm);
		});

		// Quick-entry button to insert a section separator row (mirrors Quotation)
		if (!is_sales_order_read_only(frm)) {
			frm.add_custom_button(__('Add Section / Room'), function() {
				frappe.prompt(
					{
						label: __('Section / Room Name'),
						fieldname: 'section_label',
						fieldtype: 'Data',
						reqd: 1
					},
					function(values) {
						let row = frm.add_child('items');
						row.ill_section_label = values.section_label;
						row.item_code = '';
						row.qty = 0;
						row.rate = 0;
						row.description = values.section_label;
						frm.refresh_field('items');
						frappe.show_alert({
							message: __('Section "{0}" added. Add items below it.', [values.section_label]),
							indicator: 'blue'
						});
					},
					__('New Section'),
					__('Add')
				);
			}, __('Tools'));
		}

		// Add button to generate manufacturing artifacts if there are configured fixtures
		if (frm.doc.docstatus === 1) {  // Only for submitted Sales Orders
			// Check if any line item has a configured fixture
			let has_configured_fixtures = false;
			if (frm.doc.items) {
				for (let item of frm.doc.items) {
					if (item.ill_configured_fixture) {
						has_configured_fixtures = true;
						break;
					}
				}
			}

			if (has_configured_fixtures) {
				frm.add_custom_button(__('Generate Item/BOM/WO'), function() {
					frappe.confirm(
						__('This will generate configured Items, BOMs, and Work Orders for all configured fixtures on this Sales Order. Continue?'),
						function() {
							frappe.call({
								method: 'illumenate_lighting.illumenate_lighting.api.manufacturing_generator.generate_from_sales_order',
								args: {
									sales_order: frm.doc.name
								},
								freeze: true,
								freeze_message: __('Generating manufacturing artifacts...'),
								callback: function(r) {
									if (r.message) {
										if (r.message.success) {
											frappe.msgprint({
												title: __('Success'),
												indicator: 'green',
												message: __('Manufacturing artifacts generated successfully.')
											});
											frm.reload_doc();
										} else {
											let error_msgs = r.message.messages
												.filter(m => m.severity === 'error')
												.map(m => m.text)
												.join('<br>');
											frappe.msgprint({
												title: __('Errors'),
												indicator: 'red',
												message: error_msgs || __('An error occurred during generation.')
											});
										}
									}
								}
							});
						}
					);
				}, __('Actions'));
			}
		}
	}
});

frappe.ui.form.on('Sales Order Item', {
	ill_section_label: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.ill_section_label) {
			// Auto-populate description to match the section label
			frappe.model.set_value(cdt, cdn, 'description', row.ill_section_label);
		}
	}
});
