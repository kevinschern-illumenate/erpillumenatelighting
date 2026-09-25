/* Draft-preserving quote intake and order follow-up dialogs. */
(function () {
    'use strict';
    const api = 'illumenate_lighting.illumenate_lighting.portal.';
    function dialog(title, fields, send) {
        const previousFocus = document.activeElement;
        const modal = document.createElement('dialog');
        const form = document.createElement('form');
        const heading = document.createElement('h2'); heading.textContent = title;
        heading.id = 'commercial-' + crypto.randomUUID(); modal.setAttribute('aria-labelledby', heading.id);
        form.append(heading);
        const inputs = {};
        for (const field of fields) {
            const label = document.createElement('label'); label.textContent = field.label;
            const input = document.createElement(field.type === 'textarea' ? 'textarea' : 'input');
            input.id = heading.id + '-' + field.name; input.name = field.name; label.htmlFor = input.id;
            input.className = 'form-control mb-3'; input.required = !!field.required;
            if (field.type !== 'textarea') input.type = field.type || 'text';
            if (field.type === 'file') { input.multiple = true; input.accept = '.pdf,.jpg,.jpeg,.png'; }
            else input.maxLength = field.type === 'textarea' ? 4000 : 240;
            if (field.type === 'textarea') input.rows = 4;
            inputs[field.name] = input; form.append(label, input);
        }
        const result = document.createElement('p'); result.setAttribute('role', 'status');
        const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'btn btn-secondary mr-2'; cancel.textContent = __('Cancel'); cancel.onclick = () => modal.close();
        const submit = document.createElement('button'); submit.type = 'submit'; submit.className = 'btn btn-primary'; submit.textContent = __('Submit request');
        form.append(result, cancel, submit); modal.append(form); document.body.append(modal);
        modal.addEventListener('close', () => { modal.remove(); if (previousFocus?.isConnected) previousFocus.focus(); });
        const key = crypto.randomUUID(); let sending = false;
        form.onsubmit = async event => {
            event.preventDefault(); if (sending) return;
            sending = true; submit.disabled = true; cancel.disabled = true; result.textContent = __('Sending…');
            try {
                const values = Object.fromEntries(Object.entries(inputs).filter(([, input]) => input.type !== 'file').map(([name, input]) => [name, input.value]));
                values.file_ids = inputs.files ? await PortalUploads.uploadAll(inputs.files) : [];
                const receipt = await send(values, key);
                if (receipt.new_schedule) window.location.assign('/portal/schedules/' + encodeURIComponent(receipt.new_schedule));
                else if (receipt.request_name) window.location.assign('/portal/quote-requests/' + encodeURIComponent(receipt.request_name));
                else window.location.reload();
                modal.close();
            } catch (error) { result.textContent = error.message || __('Request failed. Your draft and uploaded files are retained.'); }
            finally { sending = false; submit.disabled = false; cancel.disabled = false; }
        };
        modal.addEventListener('cancel', event => { if (sending) event.preventDefault(); });
        modal.showModal(); Object.values(inputs)[0]?.focus(); return modal;
    }
    const files = {name: 'files', type: 'file', label: __('Optional PDF/JPEG/PNG attachments: up to 10 files, 20 MiB each')};
    window.PortalCommercial = {
        quote(schedule, modified) {
            return dialog(__('Request quote / engineering review'), [
                {name: 'contact', label: __('Contact instructions')},
                {name: 'requested_date', type: 'date', label: __('Requested timing (optional)')},
                {name: 'notes', type: 'textarea', label: __('Scope, timing and questions')}, files
            ], (values, key) => PortalUploads.call(api + 'quotes.request_quote', {...values, schedule_name: schedule, expected_modified: modified, idempotency_key: key}));
        },
        order(order, revision, type) {
            const explanation = ['Reorder', 'Replacement'].includes(type)
                ? __('A new draft requires current configuration and pricing review. Explain what you need.')
                : __('Explain the requested change. Staff will review before changing the ERP order.');
            return dialog(__(type + ' request'), [{name: 'note', type: 'textarea', label: explanation, required: true}, files],
                (values, key) => PortalUploads.call(api + 'order_changes.submit', {...values, order_name: order, revision_hash: revision, request_type: type, idempotency_key: key}));
        },
        withdraw(order, revision) {
            return dialog(__('Withdraw pending order request'), [{name: 'note', type: 'textarea', label: __('Reason for withdrawal'), required: true}],
                values => PortalUploads.call(api + 'order_review.withdraw', {order_name: order, revision_hash: revision, note: values.note}));
        }
    };
    document.addEventListener('click', event => {
        const button = event.target.closest('[data-order-action]'); if (!button) return;
        const method = button.dataset.orderAction === 'Withdraw' ? 'withdraw' : 'order';
        window.PortalCommercial[method](button.dataset.order, button.dataset.revision, button.dataset.orderAction);
    });
})();
