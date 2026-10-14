// Shows a parent's portal conversation inline on its Desk form: the same thread the buyer sees.
window.illumenate_portal_conversation = function (parent_type, parent_name) {
	frappe.require(['/assets/illumenate_lighting/js/portal_uploads.js', '/assets/illumenate_lighting/js/portal_conversation.js'], () => {
		const dialog = new frappe.ui.Dialog({title: __('Portal conversation'), size: 'large', fields: [{fieldname: 'thread', fieldtype: 'HTML'}]});
		const root = document.createElement('div'); root.dataset.parentType = parent_type; root.dataset.parentName = parent_name;
		dialog.fields_dict.thread.$wrapper[0].append(root); dialog.show(); window.PortalConversation(root);
	});
};

// Rebuilt on every refresh so the thread always belongs to the record on screen.
window.illumenate_inline_conversation = function (frm) {
	frappe.require(['/assets/illumenate_lighting/js/portal_uploads.js', '/assets/illumenate_lighting/js/portal_conversation.js'], () => {
		if (frm.is_new()) return;
		frm.dashboard.wrapper.find('.ill-desk-thread-section').remove();
		const $section = frm.dashboard.add_section('<div class="ill-desk-thread"></div>', __('Portal conversation'), 'ill-desk-thread-section');
		frm.dashboard.show();
		const root = $section.find('.ill-desk-thread')[0];
		root.dataset.parentType = frm.doctype; root.dataset.parentName = frm.doc.name;
		window.PortalConversation(root);
	});
};

['Issue', 'ilL-Document-Request', 'ilL-Product-Verification-Request', 'ilL-Quote-Request', 'ilL-Order-Intake', 'ilL-Order-Change'].forEach(doctype => frappe.ui.form.on(doctype, {
	refresh(frm) {
		if (frm.is_new()) return;
		// Email-only Issues have no portal thread.
		if (doctype === 'Issue' && !frm.doc.ill_portal_request_key && !frm.doc.ill_support_owner) return;
		window.illumenate_inline_conversation(frm);
	}
}));
