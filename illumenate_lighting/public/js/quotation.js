// ilLumenate Lighting - Quotation customizations
// Adds "Section / Room" grouping support for complex multi-room quotes

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

function is_quotation_read_only(frm) {
	if (typeof frm.is_read_only === 'function') {
		return frm.is_read_only();
	}

	return !!frm.read_only || (frm.doc && frm.doc.docstatus !== 0);
}

frappe.ui.form.on('Quotation', {
	refresh: function(frm) {
		// Add a quick-entry button to insert a section separator row
		if (!is_quotation_read_only(frm)) {
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

		with_quote_order_configurator(function(configurator) {
			configurator.add_buttons(frm);
		});
	}
});

frappe.ui.form.on('Quotation Item', {
	ill_section_label: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.ill_section_label) {
			// Auto-populate description to match the section label
			frappe.model.set_value(cdt, cdn, 'description', row.ill_section_label);
		}
	}
});
