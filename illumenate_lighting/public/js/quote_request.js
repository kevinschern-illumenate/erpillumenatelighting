frappe.ui.form.on('ilL-Quote-Request', {
    refresh(frm) {
        if (frm.is_new() || ['CLOSED', 'ISSUED'].includes(frm.doc.state)) return;
        frm.add_custom_button(__('Prepare Quotation'), async () => {
            const prepare = async company => {
                const result = await frappe.call({method: 'illumenate_lighting.illumenate_lighting.portal.offers.prepare_quotation',
                    type: 'POST', args: {request_name: frm.doc.name, company}, freeze: true});
                frappe.set_route('Form', 'Quotation', result.message.quotation);
            };
            // With a single selling company there is nothing to choose.
            const companies = await frappe.db.get_list('Company', {pluck: 'name', limit: 2});
            if (companies.length === 1) return prepare(companies[0]);
            frappe.prompt({fieldname: 'company', fieldtype: 'Link', options: 'Company', reqd: 1, label: __('Selling Company'),
                default: frappe.defaults.get_user_default('Company')}, values => prepare(values.company), __('Prepare Quotation'), __('Prepare'));
        });
    }
});
