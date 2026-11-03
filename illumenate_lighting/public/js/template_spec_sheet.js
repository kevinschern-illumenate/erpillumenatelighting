/* Generate Spec on the six templates (plan Phase 3, 4.5, 4.13).
   The template must be saved first. A blocking dialog stays open while the background job
   runs (the job keeps running if the page is closed), then the form reloads. */
(() => {
    const METHOD = 'illumenate_lighting.illumenate_lighting.spec_sheet_job.';
    const POLL_MS = 3000;

    function blockingDialog() {
        const dialog = new frappe.ui.Dialog({
            title: __('Generating Spec Sheet'),
            fields: [{fieldtype: 'HTML', fieldname: 'body'}],
        });
        dialog.$wrapper.find('.modal-header .btn-modal-close').hide();
        dialog.$wrapper.modal({backdrop: 'static', keyboard: false});
        // Opaque, so the form cannot be read or edited while the job runs (4.13).
        dialog.$wrapper.css('background', 'rgba(20, 20, 20, 0.92)');
        dialog.fields_dict.body.$wrapper.html(
            `<p class="spec-sheet-message">${__('Starting...')}</p>`
            + `<p class="text-muted small">${__('When completed, this page will unfreeze and the new spec will attach to the Spec Sheet field.')}</p>`
        );
        dialog.show();
        return dialog;
    }

    function poll(frm, dialog, jobId) {
        frappe.xcall(METHOD + 'spec_sheet_job_status', {job_id: jobId}).then(status => {
            dialog.fields_dict.body.$wrapper.find('.spec-sheet-message').text(status.message || status.status);
            if (status.status === 'Done') {
                dialog.hide();
                frappe.show_alert({message: __('Spec sheet generated.'), indicator: 'green'});
                frm.reload_doc();
            } else if (status.status === 'Failed' || status.status === 'Unknown') {
                dialog.hide();
                frappe.msgprint({
                    title: __('Spec sheet not generated'),
                    message: frappe.utils.escape_html(status.message || __('The job was not found.')),
                    indicator: 'red',
                });
            } else {
                setTimeout(() => poll(frm, dialog, jobId), POLL_MS);
            }
        }).catch(() => setTimeout(() => poll(frm, dialog, jobId), POLL_MS * 2));
    }

    function generate(frm) {
        if (frm.is_dirty()) {
            frappe.msgprint(__('Save the template first.'));
            return;
        }
        const dialog = blockingDialog();
        frappe.xcall(METHOD + 'generate_spec_sheet', {
            template_doctype: frm.doctype,
            template_id: frm.doc.name,
        }).then(result => poll(frm, dialog, result.job_id)).catch(() => dialog.hide());
    }

    ['ilL-Fixture-Template', 'ilL-Tape-Neon-Template', 'ilL-LED-Sheet-Template', 'ilL-Driver-Template',
        'ilL-Controller-Template', 'ilL-Extrusion-Kit-Template'].forEach(doctype => {
        frappe.ui.form.on(doctype, {refresh(frm) {
            if (frm.is_new()) return;
            // Phase 5 changes the label to "Generate Spec & Sync to Webflow" when a sync follows.
            frm.add_custom_button(__('Generate Spec'), () => generate(frm));
        }});
    });
})();
