frappe.ui.form.on('ilL-Account-Request', {
    refresh(frm) {
        if (!['Pending', 'Information needed'].includes(frm.doc.state)) return;
        if (!frappe.user_roles.some(role => ['System Manager', 'ilL Sales Review', 'ilL Order Approver', 'ilL Support'].includes(role))) return;
        frm.add_custom_button(__('Review request'), () => {
            const d = new frappe.ui.Dialog({title: __('Account request review'), fields: [
                {fieldname: 'decision', fieldtype: 'Select', label: __('Decision'), options: ['Request information', 'Approve', 'Reject', 'Resolve profile request'], reqd: 1},
                {fieldname: 'approved_customer', fieldtype: 'Link', options: 'Customer', label: __('Verified Customer for linkage / dealer approval')},
                {fieldname: 'note', fieldtype: 'Small Text', label: __('Outcome or requested information'), reqd: 1}
            ], primary_action_label: __('Record decision'), primary_action: async values => {
                await frappe.call({method: 'illumenate_lighting.illumenate_lighting.portal.accounts.review', args: {...values, name: frm.doc.name, expected_modified: frm.doc.modified}, freeze: true});
                d.hide(); frm.reload_doc();
            }}); d.show();
        });
    }
});
