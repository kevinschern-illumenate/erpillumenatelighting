// ilLumenate Lighting - QuickBooks Online sync controls on Sales Invoice, Payment Entry and Customer.
// Shows whether the document is in QuickBooks and lets Accounts Managers push, retry or link it.

(() => {
	const API = 'illumenate_lighting.illumenate_lighting.api.qbo_push';
	const GROUP = __('QuickBooks');

	const isManager = () => ['System Manager', 'Accounts Manager'].some(role => frappe.user_roles.includes(role));

	function showResult(log) {
		if (!log) return;
		const indicator = {Synced: 'green', Skipped: 'blue', Queued: 'orange', Failed: 'red'}[log.status] || 'gray';
		const detail = log.status === 'Failed' || log.status === 'Queued' ? log.last_error : (log.warnings || '');
		frappe.show_alert({message: `${__('QuickBooks')}: ${__(log.status)}${detail ? ' — ' + frappe.utils.escape_html(detail) : ''}`, indicator}, 10);
	}

	async function renderStatus(frm) {
		if (frm.is_new()) return;
		const {message} = await frappe.call({method: `${API}.get_status`, args: {doctype: frm.doctype, name: frm.doc.name}});
		if (!message) return;
		const last = (message.logs || [])[0];
		if (message.qbo_id) {
			frm.dashboard.add_comment(__('In QuickBooks Online (Id {0}).', [message.qbo_id]), 'green', true);
		}
		if (last && last.status === 'Failed') {
			frm.dashboard.add_comment(__('QuickBooks {0} failed: {1}', [__(last.action), frappe.utils.escape_html(last.last_error || '')]), 'red', true);
		} else if (last && last.status === 'Queued' && message.push_enabled) {
			frm.dashboard.add_comment(__('QuickBooks {0} queued.', [__(last.action)]), 'orange', true);
		}
		if (last && last.warnings) {
			frm.dashboard.add_comment(frappe.utils.escape_html(last.warnings), 'yellow', true);
		}
	}

	function addButtons(frm) {
		if (frm.is_new() || !isManager()) return;
		const pushable = frm.doctype === 'Customer' || frm.doc.docstatus > 0;
		if (pushable) {
			frm.add_custom_button(__('Push now'), async () => {
				const {message} = await frappe.call({method: `${API}.push_now`, args: {doctype: frm.doctype, name: frm.doc.name}, freeze: true, freeze_message: __('Sending to QuickBooks…')});
				showResult(message);
				frm.reload_doc();
			}, GROUP);
		}
		if (!frm.doc.custom_qbo_id) {
			frm.add_custom_button(__('Link existing record'), () => {
				frappe.prompt({fieldname: 'qbo_id', fieldtype: 'Data', label: __('QuickBooks Id'), reqd: 1,
					description: __('The number after txnId= / nameId= in the QuickBooks URL of the matching record.')}, async values => {
					await frappe.call({method: `${API}.link_existing`, args: {doctype: frm.doctype, name: frm.doc.name, qbo_id: values.qbo_id}, freeze: true});
					frappe.show_alert({message: __('Linked to QuickBooks'), indicator: 'green'});
					frm.reload_doc();
				}, __('Link to QuickBooks record'), __('Link'));
			}, GROUP);
		}
		frm.add_custom_button(__('Sync log'), () => {
			frappe.set_route('List', 'ilL-QBO-Push-Log', {reference_doctype: frm.doctype, reference_name: frm.doc.name});
		}, GROUP);
	}

	for (const doctype of ['Sales Invoice', 'Payment Entry', 'Customer']) {
		frappe.ui.form.on(doctype, {
			refresh(frm) {
				addButtons(frm);
				renderStatus(frm);
			},
		});
	}
})();
