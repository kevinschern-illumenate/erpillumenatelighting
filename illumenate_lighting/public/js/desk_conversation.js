// Opens a parent's portal conversation in Desk: the same thread the buyer sees.
window.illumenate_portal_conversation = function (parent_type, parent_name) {
	frappe.require(['/assets/illumenate_lighting/js/portal_uploads.js', '/assets/illumenate_lighting/js/portal_conversation.js'], () => {
		const dialog = new frappe.ui.Dialog({title: __('Portal conversation'), size: 'large', fields: [{fieldname: 'thread', fieldtype: 'HTML'}]});
		const root = document.createElement('div'); root.dataset.parentType = parent_type; root.dataset.parentName = parent_name;
		dialog.fields_dict.thread.$wrapper[0].append(root); dialog.show(); window.PortalConversation(root);
	});
};

['Issue', 'ilL-Document-Request', 'ilL-Product-Verification-Request', 'ilL-Quote-Request', 'ilL-Order-Intake', 'ilL-Order-Change'].forEach(doctype => frappe.ui.form.on(doctype, {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__('Portal conversation'), () => window.illumenate_portal_conversation(frm.doctype, frm.doc.name));
	}
}));
