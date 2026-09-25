/* Shared staff assignment and commercial comparison actions. */
['ilL-Quote-Request', 'ilL-Order-Intake', 'ilL-Order-Change', 'ilL-Account-Request'].forEach(doctype => frappe.ui.form.on(doctype, {
    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button(__('Assign / due date'), () => frappe.prompt([
            {fieldname: 'assigned_to', fieldtype: 'Link', options: 'User', label: __('Assigned staff'), default: frm.doc.assigned_to},
            ...(doctype === 'ilL-Account-Request' ? [] : [{fieldname: 'due_date', fieldtype: 'Date', label: __('Review due'), default: frm.doc.due_date}])
        ], async values => {
            await frappe.call({method: 'illumenate_lighting.illumenate_lighting.portal.commercial_tasks.assign', type: 'POST',
                args: {...values, doctype, name: frm.doc.name, expected_modified: frm.doc.modified}, freeze: true});
            frm.reload_doc();
        }));
        if (doctype === 'ilL-Account-Request') return;
        frm.add_custom_button(__('Portal conversation'), () => {
            frappe.require(['/assets/illumenate_lighting/js/portal_uploads.js', '/assets/illumenate_lighting/js/portal_conversation.js'], () => {
                const dialog = new frappe.ui.Dialog({title: __('Portal conversation'), size: 'large', fields: [{fieldname: 'thread', fieldtype: 'HTML'}]});
                const root = document.createElement('div'); root.dataset.parentType = doctype; root.dataset.parentName = frm.doc.name;
                dialog.fields_dict.thread.$wrapper[0].append(root); dialog.show(); PortalConversation(root);
            });
        });
        if (doctype !== 'ilL-Order-Change' || ['COMPLETED', 'REJECTED'].includes(frm.doc.state)) return;
        frm.add_custom_button(__('Compare and decide'), async () => {
            const response = await frappe.call({method: 'illumenate_lighting.illumenate_lighting.portal.order_changes.review_context', args: {name: frm.doc.name}});
            const context = response.message;
            const dialog = new frappe.ui.Dialog({title: __('Review order change'), size: 'large', fields: [
                {fieldname: 'comparison', fieldtype: 'HTML'},
                {fieldname: 'action', fieldtype: 'Select', label: __('Decision'), options: 'REVIEW\nREJECT\nCOMPLETE', reqd: 1},
                {fieldname: 'result_sales_order', fieldtype: 'Link', options: 'Sales Order', label: __('Approved amended Sales Order (for a completed change)')},
                {fieldname: 'note', fieldtype: 'Small Text', label: __('Outcome visible to buyer'), reqd: 1}
            ], primary_action_label: __('Record decision'), primary_action: async values => {
                await frappe.call({method: 'illumenate_lighting.illumenate_lighting.portal.order_changes.decide', type: 'POST',
                    args: {...values, name: frm.doc.name, expected_modified: context.expected_modified, revision_hash: context.revision_hash}, freeze: true});
                dialog.hide(); frm.reload_doc();
            }});
            const pre = document.createElement('pre'); pre.style.whiteSpace = 'pre-wrap'; pre.textContent = JSON.stringify(context.changes, null, 2);
            dialog.fields_dict.comparison.$wrapper[0].append(pre); dialog.show();
        });
    }
}));
