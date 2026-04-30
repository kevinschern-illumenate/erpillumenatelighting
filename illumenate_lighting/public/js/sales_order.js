// ilLumenate Lighting - Sales Order customizations
// Adds button to generate manufacturing artifacts from configured fixtures

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

frappe.ui.form.on('Sales Order', {
	refresh: function(frm) {
		with_quote_order_configurator(function(configurator) {
			configurator.add_buttons(frm);
		});

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
