// ilLumenate Lighting - Sales Order customizations
// Adds button to generate manufacturing artifacts from configured fixtures
// Adds "Section / Room" grouping support (parity with Quotation)

const ILL_REQUEST_COLORS = {WITHDRAWN: 'red', REJECTED: 'red', INFORMATION_NEEDED: 'orange', APPROVED: 'green'};

// The portal request's state belongs on the order itself: whether the buyer
// acknowledged this revision (and what moved since), or withdrew it.
async function ill_show_portal_request(frm) {
	const response = await frappe.call({method: 'illumenate_lighting.illumenate_lighting.portal.order_review.desk_status', args: {order_name: frm.doc.name}});
	const data = response.message;
	if (!data) return null;
	const esc = frappe.utils.escape_html;
	const when = value => value ? frappe.datetime.str_to_user(value) : '';
	let text = `<strong>${__('Portal request')}:</strong> ${esc(__(data.state_label))}`;
	let color = ILL_REQUEST_COLORS[data.state] || 'blue';
	if (data.state === 'WITHDRAWN' || data.state === 'REJECTED') {
		const who = data.state === 'WITHDRAWN' ? __('The buyer withdrew this request') : __('This request was rejected');
		text = `<strong>${who}</strong>${data.last_on ? ' ' + __('on {0}', [esc(when(data.last_on))]) : ''}.`;
		if (data.last_note) text += ` ${__('Reason')}: ${esc(data.last_note)}`;
		if (!frm.doc.docstatus) text += `<br>${__('This draft can be deleted. The request and its conversation are kept.')}`;
	} else if (data.open) {
		if (!data.has_intake) text += ` · ${__('Waiting on the buyer to complete the PO, addresses and contact.')}`;
		else if (!data.confirmed_date) text += ` · ${__('Confirm a delivery date next.')}`;
		else if (data.acknowledged) { text += ` · ${__('The buyer acknowledged this revision on {0}. Ready to submit.', [esc(when(data.acknowledged_on))])}`; color = 'green'; }
		else {
			color = 'orange';
			text += ` · ${__('Waiting on the buyer to acknowledge this revision.')}`;
			if (data.changed.length) text += `<br>${__('Changed since the buyer last acknowledged')}: ${esc(data.changed.join('; '))}`;
		}
	}
	if (data.open_changes?.length) {
		color = 'orange';
		text += '<br>' + __('Buyer requests waiting on staff') + ': ' + data.open_changes.map(change =>
			`<a href="/app/ill-order-change/${encodeURIComponent(change.name)}">${esc(__(change.request_type))} (${esc(change.name)})</a>`).join(', ');
	}
	frm.dashboard.set_headline_alert(`<div>${text}</div>`, color);
	return data;
}

frappe.ui.form.on('Sales Order', {
	async refresh(frm) {
		if (frm.is_new() || !frm.doc.ill_fixture_schedule) return;
		if (!['System Manager', 'ilL Sales Review', 'ilL Order Approver'].some(role => frappe.user_roles.includes(role))) return;
		const request = await ill_show_portal_request(frm);
		if (request) {
			frm.add_custom_button(__('Intake, files and conversation'), () => frappe.set_route('Form', 'ilL-Order-Intake', request.name), __('Portal request'));
			frm.add_custom_button(__('Conversation with buyer'), () => window.illumenate_portal_conversation('ilL-Order-Intake', request.name), __('Portal request'));
		}
		// Without a request yet, Review order request starts one.
		if (frm.doc.docstatus !== 0 || (request && !request.open)) return;
		frm.add_custom_button(__('Confirm delivery date'), () => {
			frappe.prompt({fieldname: 'date', fieldtype: 'Date', label: __('Confirmed delivery date'), reqd: 1, default: frm.doc.ill_confirmed_delivery_date}, async values => {
				await frm.set_value('ill_confirmed_delivery_date', values.date);
				await frm.save();
				frappe.msgprint(__('The delivery promise is saved. Ask the buyer to review and acknowledge the current order revision before approval.'));
			}, __('Confirm delivery'), __('Save'));
		}, __('Portal request'));
		frm.add_custom_button(__('Review order request'), () => {
			const actions = {'Start review': 'REVIEW', 'Request information': 'REQUEST_INFORMATION', 'Propose changes': 'PROPOSE_CHANGES', 'Reject request': 'REJECT'};
			frappe.prompt([
				{fieldname: 'action', fieldtype: 'Select', label: __('Action'), options: Object.keys(actions).join('\n'), reqd: 1},
				{fieldname: 'note', fieldtype: 'Small Text', label: __('Message to buyer'), description: __('Posted in the buyer\'s portal conversation for this order.')}
			], async values => {
				if (frm.is_dirty()) await frm.save();
				await frappe.call({method: 'illumenate_lighting.illumenate_lighting.portal.order_review.review',
					args: {order_name: frm.doc.name, action: actions[values.action], note: values.note, expected_modified: frm.doc.modified}, type: 'POST', freeze: true});
				frappe.show_alert({message: __('Order review updated'), indicator: 'green'});
				frm.reload_doc();
			}, __('Review order request'), __('Save review'));
		});
	}
});

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

// Tags item rows with a Section / Room. The print formats group rows by
// ill_section_label, so a real item row carrying the label is all that is
// needed — a standalone separator row (no item_code, qty 0) cannot be saved
// because ERPNext rejects zero-quantity lines.
function ill_so_apply_section_label(frm) {
	frappe.prompt(
		{
			label: __('Section / Room Name'),
			fieldname: 'section_label',
			fieldtype: 'Data',
			reqd: 1
		},
		function(values) {
			const selected = (frm.get_selected() || {}).items || [];
			const targets = selected.length
				? frm.doc.items.filter(function(row) { return selected.indexOf(row.name) !== -1; })
				: frm.doc.items.filter(function(row) { return !row.ill_section_label; });

			if (!targets.length) {
				frappe.msgprint(__('Every item row already has a Section / Room. Select the rows you want to re-tag first.'));
				return;
			}

			targets.forEach(function(row) {
				frappe.model.set_value(row.doctype, row.name, 'ill_section_label', values.section_label);
			});
			frm.refresh_field('items');
			frappe.show_alert({
				message: __('Tagged {0} row(s) as "{1}".', [targets.length, values.section_label]),
				indicator: 'blue'
			});
		},
		__('Set Section / Room'),
		__('Apply')
	);
}

frappe.ui.form.on('Sales Order', {
	refresh: function(frm) {
		// "Configure & Add Fixture" (toolbar + Items grid); the shim decides
		// visibility (draft, editable, internal user) so it also works on new docs.
		with_quote_order_configurator(function(configurator) {
			configurator.add_buttons(frm);
		});

		// Tag the selected item rows (or every untagged row) with a section
		if (!is_sales_order_read_only(frm)) {
			frm.add_custom_button(__('Set Section / Room'), function() {
				ill_so_apply_section_label(frm);
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
	},

	// Removing a configured row never deletes its schedule line (the customer
	// may still rely on it); just make the disconnect visible.
	before_items_remove: function(frm, cdt, cdn) {
		const row = locals[cdt] && locals[cdt][cdn];
		if (!row || !row.ill_schedule_line_id) {
			return;
		}
		frappe.show_alert({
			message: __('Row removed. Schedule line {0} still exists on Fixture Schedule {1}.', [
				frappe.utils.escape_html(row.ill_fixture_type || row.ill_schedule_line_id),
				frappe.utils.escape_html(frm.doc.ill_fixture_schedule || '')
			]),
			indicator: 'orange'
		}, 7);
	}
});

frappe.ui.form.on('Sales Order Item', {
	ill_section_label: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		// Only a genuine separator row (no item, no qty) borrows the section
		// label as its description — never clobber a real item's build spec.
		if (row.ill_section_label && !row.item_code && !flt(row.qty)) {
			frappe.model.set_value(cdt, cdn, 'description', row.ill_section_label);
		}
	}
});
