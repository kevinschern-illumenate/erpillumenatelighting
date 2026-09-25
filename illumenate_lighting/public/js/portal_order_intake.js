(function () {
    const api = 'illumenate_lighting.illumenate_lighting.portal.order_intake.';
    const esc = value => frappe.utils.escape_html(String(value == null ? '' : value));
    window.PortalOrderIntake = {async open(target) {
        const data = await PortalUploads.call(api + 'prepare', target);
        const choices = data.choices, defaults = data.defaults || {};
        const option = (type, label) => [{value: '', label: __('Choose ' + label)}].concat((choices[type] || []).map(row => ({value: row.name, label: type === 'address' ? [row.address_title, row.address_line1, row.city].filter(Boolean).join(' - ') : [row.first_name, row.last_name, row.email_id].filter(Boolean).join(' ')})));
        const fields = [
            {fieldname: 'scope', fieldtype: 'HTML', options: '<p>' + esc(data.scope.basis) + '</p><ul>' + data.scope.lines.map(line => '<li>' + esc(line.line_id) + ': ' + esc(line.qty) + ' - ' + esc(line.product_type || line.manufacturer_type) + (line.manufacturer_type === 'OTHER' ? ' - ' + __('EXCLUDED from sellable order') : '') + '</li>').join('') + '</ul><p><a href="/portal/account#companyManagement" target="_blank" rel="noopener">' + __('Manage company addresses and contacts') + '</a></p>'},
            {fieldname: 'po_no', fieldtype: 'Data', label: __('PO number'), default: defaults.po_no || ''},
            {fieldname: 'customer_address', fieldtype: 'Select', label: __('Billing address'), options: option('address', 'billing address'), reqd: 1, default: defaults.customer_address || ''},
            {fieldname: 'shipping_address_name', fieldtype: 'Select', label: __('Shipping address'), options: option('address', 'shipping address'), reqd: 1, default: defaults.shipping_address_name || ''},
            {fieldname: 'contact_person', fieldtype: 'Select', label: __('Purchasing contact'), options: option('contact', 'contact'), reqd: 1, default: defaults.contact_person || data.purchasing_contact || ''},
            {fieldname: 'requested_date', fieldtype: 'Date', label: __('Requested delivery date (subject to confirmation)'), reqd: 1, default: defaults.requested_date || ''},
            {fieldname: 'receiving_instructions', fieldtype: 'Small Text', label: __('Receiving instructions')},
            {fieldname: 'shipping_instructions', fieldtype: 'Small Text', label: __('Shipping instructions')},
            {fieldname: 'uploads', fieldtype: 'HTML', options: '<label>' + __('PO and reference files (optional, up to 10 PDF/JPEG/PNG files, 20 MiB each)') + '<input type="file" class="form-control intake-files" multiple accept=".pdf,.jpg,.jpeg,.png"></label>'},
            {fieldname: 'acknowledge_scope', fieldtype: 'Check', label: __('I reviewed quantities and sellable scope, including exclusions. Final prices and delivery require review and acknowledgment before staff approval.'), reqd: 1},
            {fieldname: 'feedback', fieldtype: 'HTML', options: '<p role="alert" aria-live="polite" class="intake-feedback"></p>'}
        ];
        const key = crypto.randomUUID();
        const dialog = new frappe.ui.Dialog({title: __('Order request intake'), size: 'large', fields, primary_action_label: __('Submit request'), primary_action: async values => {
            if (dialog.busy) return;
            dialog.busy = true; dialog.get_primary_btn().prop('disabled', true);
            const feedback = dialog.fields_dict.feedback.$wrapper.find('.intake-feedback'); feedback.text(__('Uploading and validating request...'));
            try {
                const file_ids = await PortalUploads.uploadAll(dialog.fields_dict.uploads.$wrapper.find('input')[0]);
                const envelope = {scope_hash: data.scope_hash, expected_modified: data.expected_modified, file_ids};
                for (const key of ['po_no', 'customer_address', 'shipping_address_name', 'contact_person', 'requested_date', 'receiving_instructions', 'shipping_instructions', 'acknowledge_scope']) envelope[key] = values[key];
                const args = {...target, envelope: JSON.stringify(envelope)};
                if (!target.order_name) args.idempotency_key = key;
                const receipt = await PortalUploads.call(api + (target.order_name ? 'complete' : 'submit'), args);
                location.href = '/portal/orders/' + encodeURIComponent(receipt.sales_order);
            } catch (error) { feedback.text(error.message || __('Request failed. Your inputs and verified uploads are retained; retry.')); }
            finally { dialog.busy = false; dialog.get_primary_btn().prop('disabled', false); }
        }});
        const previous = document.activeElement;
        dialog.onhide = () => { if (previous && previous.isConnected) previous.focus(); };
        dialog.show();
    }};
})();
