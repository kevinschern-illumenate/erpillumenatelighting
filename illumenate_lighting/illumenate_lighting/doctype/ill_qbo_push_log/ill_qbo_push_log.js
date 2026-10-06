// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on('ilL-QBO-Push-Log', {
	refresh(frm) {
		if (frm.doc.reference_doctype && frm.doc.reference_name) {
			frm.add_custom_button(__('Open {0}', [__(frm.doc.reference_doctype)]), () => {
				frappe.set_route('Form', frm.doc.reference_doctype, frm.doc.reference_name);
			});
		}
		if (['Failed', 'Queued'].includes(frm.doc.status)) {
			frm.add_custom_button(__('Retry now'), async () => {
				const {message} = await frappe.call({
					method: 'illumenate_lighting.illumenate_lighting.api.qbo_push.retry',
					args: {log_name: frm.doc.name},
					freeze: true,
					freeze_message: __('Sending to QuickBooks…'),
				});
				frappe.show_alert({message: __('Status: {0}', [__(message.status)]), indicator: message.status === 'Synced' ? 'green' : 'orange'});
				frm.reload_doc();
			}).addClass('btn-primary');
		}
	},
});
