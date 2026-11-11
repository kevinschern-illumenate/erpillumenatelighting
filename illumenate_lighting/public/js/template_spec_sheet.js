/* Generate Spec on the six templates (plan Phase 3, 4.5, 4.13).
   The template must be saved first. A blocking dialog stays open while the background job
   runs (the job keeps running if the page is closed), then the form reloads. */
(() => {
    const METHOD = 'illumenate_lighting.illumenate_lighting.spec_sheet_job.';
    const POLL_MS = 3000;

    function blockingDialog(sync) {
        const dialog = new frappe.ui.Dialog({
            title: sync ? __('Generating Spec Sheet & Syncing to Webflow') : __('Generating Spec Sheet'),
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

    function finish(frm, dialog) {
        dialog.hide();
        frappe.show_alert({message: __('Spec sheet generated.'), indicator: 'green'});
        const warnings = frm.__spec_sheet_warnings || [];
        if (warnings.length) {
            frappe.msgprint({
                title: __('Spec sheet generated, with notes'),
                message: '<ul>' + warnings.map(w => `<li>${frappe.utils.escape_html(w)}</li>`).join('') + '</ul>',
                indicator: 'orange',
            });
        }
        frm.reload_doc();
    }

    function syncAfter(frm, dialog) {
        // Generate Spec & Sync to Webflow (plan 4.19): the spec is registered, then the linked
        // Webflow Product goes to Webflow through the same path as its own Sync to Webflow.
        const say = text => dialog.fields_dict.body.$wrapper.find('.spec-sheet-message').text(text);
        say(__('Spec sheet generated. Syncing to Webflow...'));
        window.illWebflowSync(frm.doc.webflow_product, say).then(result => {
            if (!result.ok) {
                frappe.msgprint({
                    title: __('Spec sheet generated, Webflow not synced'),
                    message: frappe.utils.escape_html(result.message),
                    indicator: 'red',
                });
            } else {
                frappe.show_alert({message: result.message, indicator: result.superseded ? 'orange' : 'green'});
            }
            finish(frm, dialog);
        }).catch(error => {
            frappe.msgprint({
                title: __('Spec sheet generated, Webflow not synced'),
                message: frappe.utils.escape_html((error && error.message) || __('The sync could not start.')),
                indicator: 'red',
            });
            finish(frm, dialog);
        });
    }

    function poll(frm, dialog, jobId, sync) {
        frappe.xcall(METHOD + 'spec_sheet_job_status', {job_id: jobId}).then(status => {
            dialog.fields_dict.body.$wrapper.find('.spec-sheet-message').text(status.message || status.status);
            if (status.status === 'Done') {
                if (sync) {
                    syncAfter(frm, dialog);
                } else {
                    finish(frm, dialog);
                }
            } else if (status.status === 'Failed' || status.status === 'Unknown') {
                dialog.hide();
                frappe.msgprint({
                    title: __('Spec sheet not generated'),
                    message: frappe.utils.escape_html(status.message || __('The job was not found.')),
                    indicator: 'red',
                });
            } else {
                setTimeout(() => poll(frm, dialog, jobId, sync), POLL_MS);
            }
        }).catch(() => setTimeout(() => poll(frm, dialog, jobId, sync), POLL_MS * 2));
    }

    function generate(frm, sync) {
        if (frm.is_dirty()) {
            frappe.msgprint(__('Save the template first.'));
            return;
        }
        // Start the job first: the server checks the template and lists anything missing. The
        // blocking dialog opens only once the job has been accepted.
        frappe.call({
            method: METHOD + 'generate_spec_sheet',
            args: {template_doctype: frm.doctype, template_id: frm.doc.name},
            freeze: true,
            freeze_message: __('Checking the template...'),
        }).then(r => {
            const result = r && r.message;
            if (!result || !result.job_id) return;
            frm.__spec_sheet_warnings = result.warnings || [];
            poll(frm, blockingDialog(sync), result.job_id, sync);
        });
    }

    ['ilL-Fixture-Template', 'ilL-Tape-Neon-Template', 'ilL-LED-Sheet-Template', 'ilL-Driver-Template',
        'ilL-Controller-Template', 'ilL-Extrusion-Kit-Template'].forEach(doctype => {
        frappe.ui.form.on(doctype, {refresh(frm) {
            if (frm.is_new()) return;
            // With a linked Webflow Product the spec is generated, then the product is synced
            // (plan 4.19); without one it only generates the spec.
            const sync = Boolean(frm.doc.webflow_product);
            const button = frm.add_custom_button(
                sync ? __('Generate Spec & Sync to Webflow') : __('Generate Spec'),
                () => generate(frm, sync)
            );
            // Owner, 2026-11-11: accent with primary text when it also syncs; light blue with
            // secondary text when it only generates the spec.
            const [background, color] = sync ? ['#fdc757', '#172e48'] : ['#e6eef4', '#00588c'];
            if (button && button.css) {
                button.css({'background-color': background, color, 'border-color': background, 'font-weight': 'bold'});
            }
        }});
    });
})();
