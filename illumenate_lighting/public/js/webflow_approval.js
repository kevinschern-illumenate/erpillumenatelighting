/* Webflow approvals banner on the Webflow Product (plan 4.19 Q5, Q6).

   A restore of an archived product, or archiving a page that was ever published, waits for
   approval (ilL-Webflow-Approval). While one is pending the form shows an orange banner with
   what would happen and Approve / Reject; nothing for the product goes to Webflow until then.
   Approve sends the change through the normal sync; Reject puts the status back. */
(function () {
    const API = 'illumenate_lighting.illumenate_lighting.webflow_approvals.';
    const esc = value => frappe.utils.escape_html(value == null ? '' : String(value));

    function banner(row) {
        const buttons = row.can_decide
            ? `<div style="margin-top: 8px;">
                    <button class="btn btn-xs btn-primary" data-ill-approval="approve">${esc(__('Approve'))}</button>
                    <button class="btn btn-xs btn-default" data-ill-approval="reject" style="margin-left: 6px;">${esc(__('Reject'))}</button>
               </div>`
            : `<div class="text-muted" style="margin-top: 6px;">${esc(__('Only the owner or a user who can edit this product can decide it.'))}</div>`;
        return `<div class="ill-webflow-approval">
                <strong>${esc(__('Waiting for approval'))}:</strong> ${esc(row.summary || row.action)}
                <div class="text-muted">${esc(__('Nothing for this product goes to Webflow until this is approved or rejected.'))}
                    ${esc(__('Requested by'))} ${esc(row.requested_by)} (${esc(row.name)}).</div>
                ${buttons}
            </div>`;
    }

    function decide(frm, row, action) {
        const approve = action === 'approve';
        const question = approve
            ? __('Approve and send this change to Webflow now?') + '<br><br>' + esc(row.summary)
            : __('Reject? Webflow is left as it is and the status goes back to {0}.', [esc(row.from_status)]);
        frappe.confirm(question, () => {
            frappe.xcall(API + (approve ? 'approve' : 'reject'), {name: row.name}).then(result => {
                let message = approve ? __('Approved.') : __('Rejected; the status was put back.');
                let indicator = 'green';
                if (approve && result && result.sync_error) {
                    message = __('Approved, but the sync did not start: {0}', [esc(result.sync_error)]);
                    indicator = 'orange';
                } else if (approve && result && result.sync) {
                    message = __('Approved; sent to Webflow.');
                }
                frappe.show_alert({message, indicator});
                frm.reload_doc();
            });
        });
    }

    function show(frm) {
        if (frm.is_new()) return;
        const name = frm.doc.name;
        frappe.xcall(API + 'get_pending', {product: name}).then(row => {
            if (frm.doc.name !== name) return;
            if (!row) {
                if (frm.__ill_approval_shown) {
                    frm.set_intro('');
                    frm.__ill_approval_shown = false;
                }
                return;
            }
            frm.__ill_approval_shown = true;
            frm.set_intro(banner(row), 'orange');
            frm.$wrapper.off('click.illApproval').on('click.illApproval', '[data-ill-approval]', event => {
                event.preventDefault();
                decide(frm, row, $(event.currentTarget).attr('data-ill-approval'));
            });
        });
    }

    window.illWebflowApproval = {show, banner};

    frappe.ui.form.on('ilL-Webflow-Product', {
        refresh(frm) {
            show(frm);
        },
    });
})();
