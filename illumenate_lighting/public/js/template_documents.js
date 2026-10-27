/* Other Documents on a template: the spec sheet has its own field, so it is not offered here.
   The Webflow Product still lists it under "Spec Sheet", copied from that field on save.
   custom_documents is a site Custom Field the app does not ship; skip forms without it. */
['ilL-Fixture-Template','ilL-Tape-Neon-Template','ilL-LED-Sheet-Template','ilL-Driver-Template','ilL-Controller-Template','ilL-Extrusion-Kit-Template'].forEach(doctype => {
    frappe.ui.form.on(doctype, {onload_post_render(frm) {
        const grid = frm.fields_dict.custom_documents && frm.fields_dict.custom_documents.grid;
        const field = frappe.meta.get_docfield('ilL-Child-Webflow-Document', 'document_type');
        if (!grid || !field) return;
        const options = (field.options || '').split('\n').filter(option => option !== 'Spec Sheet');
        grid.update_docfield_property('document_type', 'options', options.join('\n'));
    }});
});
