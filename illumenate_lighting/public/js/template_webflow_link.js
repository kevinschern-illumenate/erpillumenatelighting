/* The template owns its link to a Webflow Product (plan 4.2). The Webflow Product field is
   editable while empty; once set, it changes only through Unlink Webflow Product, which
   clears both sides in one server call (template_link.unlink_webflow_product). */
['ilL-Fixture-Template','ilL-Tape-Neon-Template','ilL-LED-Sheet-Template','ilL-Driver-Template','ilL-Controller-Template','ilL-Extrusion-Kit-Template'].forEach(doctype => {
    frappe.ui.form.on(doctype, {refresh(frm) {
        if (frm.is_new() || !frm.doc.webflow_product) return;
        frm.add_custom_button(__('Unlink Webflow Product'), () => {
            if (frm.is_dirty()) {
                frappe.msgprint(__('Save the template first.'));
                return;
            }
            frappe.confirm(
                __('Unlink Webflow Product {0} from this template? The product keeps its data but no longer follows this template.', [frm.doc.webflow_product]),
                () => frappe.xcall('illumenate_lighting.illumenate_lighting.template_link.unlink_webflow_product', {
                    template_doctype: frm.doctype,
                    template_id: frm.doc.name,
                }).then(() => frm.reload_doc())
            );
        }, __('Actions'));
    }});
});
