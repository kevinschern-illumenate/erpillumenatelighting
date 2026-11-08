/* One sync path to Webflow (plan 4.19, owner 2026-11-05).

   illWebflowSync(product, onMessage) stages the Webflow Product through the publication
   pipeline (webflow_export_v2.trigger_sync_v2 -> ilL-Publish-Job -> n8n W2) and waits for every
   target brand to finish. Published and Discontinued products are published; a Webflow Draft
   is staged only (or published hidden once it was ever published). Used by the Webflow
   Product's "Sync to Webflow" and the template's "Generate Spec & Sync to Webflow". Resolves
   {ok, message, superseded}. */
window.illWebflowSync = window.illWebflowSync || function (product, onMessage) {
    const api = 'illumenate_lighting.illumenate_lighting.api.webflow_export_v2.';
    const POLL_MS = 3000;
    const TIMEOUT_MS = 180000;
    const say = text => onMessage && onMessage(text);
    return frappe.xcall(api + 'get_sync_progress', {docname: product}).then(baseline => {
        const since = baseline && baseline.server_time;
        say(__('Sending to Webflow...'));
        return frappe.xcall(api + 'trigger_sync_v2', {docname: product}).then(result => {
            const jobs = ((result && result.jobs) || []).filter(Boolean);
            if (!jobs.length) {
                return {ok: false, message: __('Nothing was sent: the product is not ready for any brand.')};
            }
            say(__('Waiting for Webflow...'));
            const started = Date.now();
            return new Promise(resolve => {
                const check = () => {
                    frappe.xcall(api + 'get_sync_progress', {docname: product, since}).then(progress => {
                        if (progress && progress.failed) {
                            const errors = (progress.brands || []).filter(row => row.state === 'failed')
                                .map(row => `${row.brand}: ${row.error || __('failed')}`);
                            resolve({ok: false, message: errors.join('; ') || __('The sync failed.')});
                        } else if (progress && progress.complete) {
                            const superseded = (progress.brands || []).some(row => row.state === 'superseded');
                            resolve({ok: true, superseded, message: superseded
                                ? __('Webflow finished an older revision. Sync again for the latest changes.')
                                : __('Webflow sync finished.')});
                        } else if (Date.now() - started > TIMEOUT_MS) {
                            resolve({ok: false, message: __('Not confirmed yet. It may still be running; check the product later.')});
                        } else {
                            setTimeout(check, POLL_MS);
                        }
                    }).catch(() => setTimeout(check, POLL_MS * 2));
                };
                setTimeout(check, POLL_MS);
            });
        });
    });
};
