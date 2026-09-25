/* Account requests and company records share server-side ownership checks. */
(function () {
    const method = 'illumenate_lighting.illumenate_lighting.portal.accounts.';
    const call = (name, args) => PortalUploads.call(method + name, args || {});
    const escape = value => frappe.utils.escape_html(String(value == null ? '' : value));
    function dialog(title, fields, submit) {
        const previous = document.activeElement;
        const form = new frappe.ui.Dialog({title: __(title), fields, primary_action_label: __('Save'),
            primary_action: async values => {
                if (form.busy) return;
                form.busy = true; form.get_primary_btn().prop('disabled', true);
                try { await submit(values); form.hide(); }
                catch (error) { frappe.msgprint(escape(error.message)); }
                finally { form.busy = false; form.get_primary_btn().prop('disabled', false); }
            }});
        form.onhide = () => { if (previous && previous.isConnected) previous.focus(); };
        form.show(); return form;
    }
    async function refresh(container) {
        container.setAttribute('aria-busy', 'true');
        try {
            const data = await call('overview');
            container.replaceChildren();
            const controls = document.createElement('div'); controls.className = 'd-flex flex-wrap mb-3';
            function button(parent, text, action) {
                const element = document.createElement('button'); element.type = 'button'; element.className = 'btn btn-sm btn-outline-primary m-1';
                element.textContent = __(text); element.addEventListener('click', () => Promise.resolve(action()).catch(error => frappe.msgprint(escape(error.message)))); parent.append(element);
            }
            button(controls, 'Request account or company change', () => dialog('Account request', [
                {fieldname: 'request_type', fieldtype: 'Select', options: ['Dealer application', 'Company linkage', 'Profile change', 'Account closure'], label: __('Request'), reqd: 1},
                {fieldname: 'note', fieldtype: 'Small Text', label: __('Details for staff review'), reqd: 1}
            ], async values => { const receipt = await call('request_change', values); frappe.show_alert(__('Request received: {0}', [receipt.request])); await refresh(container); }));
            if (data.can_manage) {
                button(controls, 'Invite company member', () => dialog('Invite company member', [
                    {fieldname: 'email', fieldtype: 'Data', options: 'Email', label: __('Email'), reqd: 1},
                    {fieldname: 'first_name', fieldtype: 'Data', label: __('First name'), reqd: 1},
                    {fieldname: 'last_name', fieldtype: 'Data', label: __('Last name')},
                    {fieldname: 'scope_note', fieldtype: 'HTML', options: '<p>' + __('Members receive company visibility without dealer purchasing or staff rights. The recipient must sign in with the invited email and accept the link within seven days.') + '</p>'}
                ], async values => {
                    const receipt = await call('invite', {email: values.email, first_name: values.first_name, last_name: values.last_name || ''});
                    const url = location.origin + receipt.invite_url;
                    frappe.msgprint({title: __('Invitation ready to share'), message: '<p>' + __('Send this one-use link to {0}:', [escape(receipt.email)]) + '</p><input class="form-control" readonly aria-label="Invitation link" value="' + escape(url) + '"><p>' + __('No access is granted until the recipient accepts.') + '</p>'});
                    await refresh(container);
                }));
                for (const doctype of ['Address', 'Contact']) button(controls, 'Add ' + doctype.toLowerCase(), () => edit(doctype));
            }
            button(controls, 'Refresh', () => refresh(container)); container.append(controls);
            function section(title, rows, render) {
                const heading = document.createElement('h3'); heading.className = 'h5 mt-4'; heading.textContent = __(title); container.append(heading);
                if (!rows.length) { const empty = document.createElement('p'); empty.textContent = __('No records yet.'); container.append(empty); }
                rows.forEach(row => { const block = document.createElement('div'); block.className = 'border rounded p-2 mb-2'; render(block, row); container.append(block); });
            }
            function text(parent, value) { const p = document.createElement('p'); p.className = 'mb-1'; p.textContent = value || ''; parent.append(p); }
            function edit(doctype, row) {
                const names = doctype === 'Address' ? ['address_title', 'address_type', 'address_line1', 'address_line2', 'city', 'state', 'country', 'pincode', 'phone', 'email_id'] : ['first_name', 'last_name', 'designation', 'phone', 'email_id'];
                const required = doctype === 'Address' ? ['address_type', 'address_line1', 'city', 'country'] : ['first_name'];
                const fields = names.map(name => ({fieldname: name, fieldtype: name === 'address_type' ? 'Select' : name === 'country' ? 'Link' : 'Data',
                    options: name === 'address_type' ? 'Billing\nShipping\nOffice\nOther' : name === 'country' ? 'Country' : name === 'email_id' ? 'Email' : undefined,
                    label: __(name.replaceAll('_', ' ')), default: row && row[name] || '', reqd: required.includes(name)}));
                dialog(row ? 'Request ' + doctype.toLowerCase() + ' change' : 'Add ' + doctype.toLowerCase(), fields, async values => {
                    const receipt = await call('save_record', {doctype, values: JSON.stringify(values), name: row && row.name, expected_modified: row && row.modified});
                    if (receipt.request) frappe.show_alert(__('Change submitted for review: {0}', [receipt.request]));
                    await refresh(container);
                });
            }
            if (data.can_manage) {
                for (const doctype of ['Address', 'Contact']) section(doctype + ' records', data[doctype.toLowerCase()] || [], (block, row) => {
                    text(block, doctype === 'Address' ? [row.address_title, row.address_line1, row.address_line2, row.city, row.state, row.pincode, row.country].filter(Boolean).join(', ') : [row.first_name, row.last_name, row.email_id, row.phone].filter(Boolean).join(' '));
                    button(block, 'Request edit', () => edit(doctype, row));
                    button(block, 'Request archive', async () => { await call('archive_record', {doctype, name: row.name, expected_modified: row.modified}); await refresh(container); });
                    if (doctype === 'Contact') {
                        if (data.purchasing_contact === row.name) text(block, __('Purchasing contact'));
                        else button(block, 'Use as purchasing contact', async () => { await call('set_purchasing_contact', {contact: row.name}); await refresh(container); });
                    }
                });
                section('Company members', data.members || [], (block, row) => {
                    text(block, row.full_name + ' (' + row.name + ') - ' + (row.enabled ? __('Active') : __('Disabled')));
                    if (row.enabled && row.user_type === 'Website User' && row.name !== frappe.session.user) button(block, 'Disable invited member', () => new Promise(resolve => frappe.confirm(__('Disable this member’s portal account? Historic actions remain attributed to them.'), async () => { try { await call('disable_member', {user: row.name}); await refresh(container); } catch (error) { frappe.msgprint(escape(error.message)); } resolve(); }, resolve)));
                });
                section('Invitations', data.invitations || [], (block, row) => {
                    text(block, row.email + ' - ' + row.state + ' - ' + __('Expires') + ' ' + row.expires_on);
                    if (row.state === 'Pending') button(block, 'Revoke', async () => { await call('revoke_invitation', {name: row.name}); await refresh(container); });
                });
            }
            section('Account request history', data.requests || [], (block, row) => {
                text(block, row.name + ': ' + row.request_type + ' - ' + row.state); text(block, row.staff_note);
                if (row.state === 'Information needed') button(block, 'Reply', () => dialog('Requested information', [{fieldname: 'message', fieldtype: 'Small Text', label: __('Reply'), reqd: 1}], async values => { await call('reply', {name: row.name, message: values.message}); await refresh(container); }));
            });
        } catch (error) { container.textContent = __('Account details unavailable. Reload or retry.') + ' ' + error.message; }
        finally { container.setAttribute('aria-busy', 'false'); }
    }
    window.PortalAccounts = {mount: refresh};
})();
