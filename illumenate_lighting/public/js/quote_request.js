frappe.ui.form.on('ilL-Quote-Request', {
    refresh(frm) {
        if (frm.is_new() || ['CLOSED', 'ISSUED'].includes(frm.doc.state)) return;
        frm.add_custom_button(__('Prepare Quotation'), () => {
            frappe.prompt({fieldname: 'company', fieldtype: 'Link', options: 'Company', reqd: 1, label: __('Selling Company')}, async values => {
                const result = await frappe.call({method: 'illumenate_lighting.illumenate_lighting.portal.offers.prepare_quotation',
                    type: 'POST', args: {request_name: frm.doc.name, company: values.company}, freeze: true});
                frappe.set_route('Form', 'Quotation', result.message.quotation);
            }, __('Prepare Quotation'), __('Prepare'));
        });
    }
});
