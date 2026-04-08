// ilLumenate Lighting - Quotation customizations
// Adds "Section / Room" grouping support for complex multi-room quotes

frappe.ui.form.on('Quotation', {
	refresh: function(frm) {
		// Add a quick-entry button to insert a section separator row
		if (!frm.is_read_only()) {
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
