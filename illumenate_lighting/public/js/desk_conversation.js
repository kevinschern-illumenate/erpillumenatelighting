['Issue', 'ilL-Document-Request'].forEach(doctype => frappe.ui.form.on(doctype, {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__('Portal conversation'), () => {
			frappe.require(['/assets/illumenate_lighting/js/portal_uploads.js', '/assets/illumenate_lighting/js/portal_conversation.js'], () => {
				const dialog = new frappe.ui.Dialog({title: __('Portal conversation'), size: 'large', fields: [{fieldname: 'thread', fieldtype: 'HTML'}]});
				const root = document.createElement('div'); root.dataset.parentType = frm.doctype; root.dataset.parentName = frm.doc.name;
				dialog.fields_dict.thread.$wrapper[0].append(root); dialog.show(); window.PortalConversation(root);
			});
		});
	}
}));
