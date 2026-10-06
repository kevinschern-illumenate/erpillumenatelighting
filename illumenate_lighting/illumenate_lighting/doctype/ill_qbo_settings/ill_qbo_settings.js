// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on('ilL-QBO-Settings', {
	refresh(frm) {
		const API = 'illumenate_lighting.illumenate_lighting.api.qbo_push';

		frm.add_custom_button(__('Test QuickBooks connection'), async () => {
			if (frm.is_dirty()) await frm.save();
			const {message} = await frappe.call({method: `${API}.test_connection`, freeze: true, freeze_message: __('Asking QuickBooks through n8n…')});
			const rows = (message.checks || []).map(c => `<li>${c.ok ? '✅' : '❌'} ${frappe.utils.escape_html(c.entity)} “${frappe.utils.escape_html(c.name)}” ${c.ok ? '(Id ' + c.id + ')' : '— ' + frappe.utils.escape_html(c.error)}</li>`);
			frappe.msgprint({
				title: __('Connected to {0}', [frappe.utils.escape_html(message.company_name || '')]),
				message: rows.length ? `<ul>${rows.join('')}</ul>` : __('Connection works.'),
				indicator: (message.checks || []).every(c => c.ok) ? 'green' : 'orange',
			});
		}, __('Outbound'));

		frm.add_custom_button(__('Retry all failed pushes'), async () => {
			const {message} = await frappe.call({method: `${API}.retry_failed`, freeze: true});
			frappe.show_alert({message: __('{0} push(es) re-queued', [message]), indicator: 'green'});
		}, __('Outbound'));

		frm.add_custom_button(__('Backfill…'), () => {
			frappe.prompt([
				{fieldname: 'from_date', fieldtype: 'Date', label: __('From posting date'), reqd: 1},
				{fieldname: 'to_date', fieldtype: 'Date', label: __('To posting date')},
				{fieldname: 'include_payments', fieldtype: 'Check', label: __('Include customer payments'), default: 1},
			], async values => {
				const {message} = await frappe.call({method: `${API}.backfill`, args: values, freeze: true});
				frappe.msgprint(__('Queued {0} Sales Invoice(s) and {1} Payment Entry(s). Watch progress in ilL-QBO-Push-Log.', [message['Sales Invoice'], message['Payment Entry']]));
			}, __('Push existing documents to QuickBooks'), __('Queue'));
		}, __('Outbound'));

		frm.add_custom_button(__('Push log'), () => frappe.set_route('List', 'ilL-QBO-Push-Log'), __('Logs'));
		frm.add_custom_button(__('Inbound sync log'), () => frappe.set_route('List', 'ilL-QBO-Sync-Log'), __('Logs'));
	},
});
