/* Automatic Webflow push state on the Webflow Product (plan 4.19, sync rebuild step 3).

   A synced product pushes to Webflow 2 minutes after its last save. One small line above the
   form says when the waiting push is due, that it is held (site config webflow_auto_push is
   off) or waits for an approval, and when a failed push retries. Nothing shows otherwise. */
(function () {
    const API = 'illumenate_lighting.illumenate_lighting.webflow_auto_push.get_status';
    const esc = value => frappe.utils.escape_html(value == null ? '' : String(value));
    const time = value => String(value || '').slice(11, 16);

    function lines(status) {
        const out = [];
        // What Webflow shows when the template's Product Status overrides this product's
        // Webflow Status (owner, 2026-11-08).
        if (status.effective) out.push(esc(status.effective));
        (status.waiting || []).forEach(row => {
            if (row.state === 'held') {
                out.push(__('Automatic push to {0} held: automatic pushes are off (site config webflow_auto_push).', [esc(row.brand)]));
            } else if (row.state === 'approval') {
                out.push(__('Automatic push to {0} waits for the pending approval.', [esc(row.brand)]));
            } else {
                out.push(__('Automatic push to {0} waiting: due {1}.', [esc(row.brand), esc(time(row.due_at))]));
            }
        });
        (status.retries || []).forEach(row => {
            out.push(__('Failed push to {0} retries at {1}.', [esc(row.brand), esc(time(row.next_attempt_on))]));
        });
        return out;
    }

    function render(frm, status) {
        if (frm.__ill_auto_push_el) {
            frm.__ill_auto_push_el.remove();
            frm.__ill_auto_push_el = null;
        }
        const text = status ? lines(status) : [];
        if (!text.length || !frm.layout || !frm.layout.wrapper) return;
        frm.__ill_auto_push_el = $(`<div class="ill-webflow-auto-push text-muted small" style="margin: 0 0 8px;">${text.join('<br>')}</div>`);
        $(frm.layout.wrapper).prepend(frm.__ill_auto_push_el);
    }

    function show(frm) {
        if (frm.is_new()) return render(frm, null);
        const name = frm.doc.name;
        frappe.xcall(API, {product: name}).then(status => {
            if (frm.doc.name === name) render(frm, status);
        });
    }

    window.illWebflowAutoPush = {show, lines};

    frappe.ui.form.on('ilL-Webflow-Product', {
        refresh(frm) {
            show(frm);
        },
    });
})();
