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

		// "Get Items From > Fixture Schedule" — pull all line items from a
		// pre-existing fixture schedule (typically created in the portal).
		if (!is_quotation_read_only(frm)) {
			frm.add_custom_button(__('Fixture Schedule'), function() {
				ill_open_fixture_schedule_picker(frm);
			}, __('Get Items From'));
		}
	}
});

function ill_open_fixture_schedule_picker(frm) {
	const customer = (frm.doc.quotation_to === 'Customer') ? frm.doc.party_name : null;

	const dialog = new frappe.ui.Dialog({
		title: __('Get Items From Fixture Schedule'),
		fields: [
			{
				fieldname: 'fixture_schedule',
				fieldtype: 'Link',
				label: __('Fixture Schedule'),
				options: 'ilL-Project-Fixture-Schedule',
				reqd: 1,
				get_query: function() {
					const filters = {};
					if (customer) {
						filters.customer = customer;
					}
					return { filters: filters };
				}
			},
			{
				fieldname: 'preview_html',
				fieldtype: 'HTML'
			},
			{
				fieldname: 'options_section',
				fieldtype: 'Section Break',
				label: __('Options')
			},
			{
				fieldname: 'include_accessories',
				fieldtype: 'Check',
				label: __('Include Accessories / Power Supplies'),
				default: 1
			}
		],
		primary_action_label: __('Add Items'),
		primary_action: function(values) {
			if (!values.fixture_schedule) {
				frappe.msgprint(__('Please select a Fixture Schedule.'));
				return;
			}
			frappe.call({
				method: 'illumenate_lighting.illumenate_lighting.api.quote_from_schedule.add_schedule_to_quotation',
				args: {
					quotation: frm.doc.name,
					fixture_schedule: values.fixture_schedule,
					include_accessories: values.include_accessories ? 1 : 0,
					include_other: 0
				},
				freeze: true,
				freeze_message: __('Adding schedule items to quotation...'),
				callback: function(r) {
					if (!r.message) {
						return;
					}
					dialog.hide();
					ill_show_schedule_import_result(frm, r.message);
				}
			});
		}
	});

	dialog.fields_dict.fixture_schedule.df.onchange = function() {
		const schedule = dialog.get_value('fixture_schedule');
		const wrapper = dialog.fields_dict.preview_html.$wrapper;
		if (!schedule) {
			wrapper.empty();
			return;
		}
		wrapper.html(`<div class="text-muted">${__('Loading preview...')}</div>`);
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.quote_from_schedule.get_schedule_summary',
			args: { fixture_schedule: schedule },
			callback: function(r) {
				if (!r.message) {
					wrapper.empty();
					return;
				}
				wrapper.html(ill_render_schedule_preview(r.message));
			}
		});
	};

	dialog.show();
}

function ill_render_schedule_preview(data) {
	const s = data.summary || {};
	const rows = [
		[__('Configured Fixtures'), s.fixtures || 0],
		[__('LED Tape / Neon'), s.tape_neon || 0],
		[__('Extrusion Kits'), s.kits || 0],
		[__('Accessories / Power Supplies'), s.accessories || 0],
		[__('Other Manufacturer (not imported)'), s.other || 0],
		[__('Unconfigured (skipped)'), s.unconfigured || 0]
	];

	let body = rows.map(function(row) {
		return `<tr><td>${row[0]}</td><td class="text-right">${row[1]}</td></tr>`;
	}).join('');

	return `
		<div style="margin-top: 10px;">
			<div><b>${frappe.utils.escape_html(data.schedule_name || data.fixture_schedule)}</b>
				<span class="text-muted">(${__('Status')}: ${frappe.utils.escape_html(data.status || '')})</span></div>
			<table class="table table-bordered" style="margin-top: 8px; margin-bottom: 0;">
				<tbody>${body}</tbody>
			</table>
		</div>
	`;
}

function ill_show_schedule_import_result(frm, result) {
	frm.reload_doc();

	const parts = [];
	if (result.fixtures) parts.push(__('{0} configured fixture(s)', [result.fixtures]));
	if (result.tape_neon) parts.push(__('{0} tape/neon line(s)', [result.tape_neon]));
	if (result.kits) parts.push(__('{0} extrusion kit(s)', [result.kits]));
	if (result.accessories) parts.push(__('{0} accessory line(s)', [result.accessories]));

	let message = '';
	if (result.rows_added) {
		message += `<p>${__('Added {0} item row(s) to this quotation.', [result.rows_added])}</p>`;
		if (parts.length) {
			message += `<p>${parts.join(', ')}</p>`;
		}
	} else {
		message += `<p>${__('No item rows were added.')}</p>`;
	}

	if (result.messages && result.messages.length) {
		const notes = result.messages
			.map(function(m) { return `<li>${frappe.utils.escape_html(m)}</li>`; })
			.join('');
		message += `<p>${__('Notes:')}</p><ul>${notes}</ul>`;
	}

	frappe.msgprint({
		title: result.rows_added ? __('Items Added') : __('Nothing Added'),
		indicator: result.rows_added ? 'green' : 'orange',
		message: message
	});
}

frappe.ui.form.on('Quotation Item', {
	ill_section_label: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.ill_section_label) {
			// Auto-populate description to match the section label
			frappe.model.set_value(cdt, cdn, 'description', row.ill_section_label);
		}
	}
});
