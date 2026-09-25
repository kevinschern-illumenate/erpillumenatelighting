frappe.ui.form.on('ilL-Portal-Delivery', {
	refresh(frm) {
		if (frm.doc.email_queue) {
			frm.add_custom_button(__('Inspect Email Queue'), () => frappe.set_route('Form', 'Email Queue', frm.doc.email_queue));
		} else if (frm.doc.state === 'FAILED') {
			frm.add_custom_button(__('Retry queue creation'), async () => {
				await frappe.call({method: 'illumenate_lighting.illumenate_lighting.portal.outbox.retry', args:{name:frm.doc.name}, type:'POST', freeze:true});
				frm.reload_doc();
			});
		}
	}
});
