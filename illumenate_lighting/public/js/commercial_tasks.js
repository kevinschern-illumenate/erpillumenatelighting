/* Shared staff assignment and commercial comparison actions. */
// What the buyer asked for, and what moved on the order since they asked.
function ill_change_comparison(context) {
    const esc = value => frappe.utils.escape_html(value === null || value === undefined || value === '' ? '-' : String(value));
    const label = key => esc(frappe.unscrub(key.replace(/^ill_/, '')));
    let html = `<p><strong>${esc(__(context.request_type))} ${__('request')}:</strong> ${esc(context.note)}</p>`;
    const fields = Object.entries(context.changes || {});
    const lines = context.lines || [];
    if (!fields.length && !lines.length) return html + `<p class="text-muted">${__('The order has not changed since the buyer made this request.')}</p>`;
    html += `<p class="text-muted">${__('Changed on the order since the request')}:</p>`;
    if (fields.length) html += `<table class="table table-sm table-bordered"><thead><tr><th>${__('Field')}</th><th>${__('Before')}</th><th>${__('Now')}</th></tr></thead><tbody>`
        + fields.map(([key, value]) => `<tr><td>${label(key)}</td><td>${esc(value.before)}</td><td>${esc(value.after)}</td></tr>`).join('') + '</tbody></table>';
    if (lines.length) html += `<table class="table table-sm table-bordered"><thead><tr><th>${__('Item')}</th><th>${__('Qty')}</th><th>${__('Rate')}</th><th>${__('Change')}</th></tr></thead><tbody>`
        + lines.map(line => `<tr><td>${esc(line.item_code)}</td><td>${esc(line.qty)}${line.was && line.changed.includes('qty') ? ` (${__('was')} ${esc(line.was.qty)})` : ''}</td><td>${esc(line.rate)}${line.was && line.changed.includes('rate') ? ` (${__('was')} ${esc(line.was.rate)})` : ''}</td><td>${esc(__(frappe.unscrub(line.status)))}</td></tr>`).join('') + '</tbody></table>';
    return html;
}
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
        // The Portal conversation button comes from desk_conversation.js.
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
            dialog.fields_dict.comparison.$wrapper.html(ill_change_comparison(context)); dialog.show();
        });
    }
}));
