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

/* Going Active + Live without a Webflow Product (plan 4.5, D3; owner 2026-11-08): a popup with
   Create new (the product is created from the template's name, slug, type and brand, all
   editable), Link existing (a product of the right type that no template links yet) and Cancel
   (the Product Status goes back). Create and link both finish with the template's normal save,
   which writes both sides and keeps any other unsaved edits. */
(function () {
    const LIVE = 'Active + Live';
    const API = 'illumenate_lighting.illumenate_lighting.template_link.';
    const TEMPLATES = ['ilL-Fixture-Template', 'ilL-Tape-Neon-Template', 'ilL-LED-Sheet-Template',
        'ilL-Driver-Template', 'ilL-Controller-Template', 'ilL-Extrusion-Kit-Template'];

    function revert(frm, previous) {
        frm.__ill_reverting = true;
        Promise.resolve(frm.set_value('product_status', previous || '')).finally(() => { frm.__ill_reverting = false; });
    }

    function link(frm, product, dialog) {
        return Promise.resolve(frm.set_value('webflow_product', product))
            .then(() => frm.save())
            .then(() => { dialog.__done = true; dialog.hide(); });
    }

    function open(frm, previous, defaults) {
        const single = defaults.product_types.length === 1;
        const dialog = new frappe.ui.Dialog({
            title: __('This template needs a Webflow Product'),
            fields: [
                {fieldtype: 'HTML', options: `<p>${__('An Active + Live template is listed on the website through its Webflow Product. Create one now, or link an existing one.')}</p>`},
                {fieldname: 'choice', fieldtype: 'Select', label: __('Webflow Product'), options: ['Create new', 'Link existing'], default: 'Create new', reqd: 1},
                {fieldname: 'product_name', fieldtype: 'Data', label: __('Product Name'), default: defaults.product_name, depends_on: "eval:doc.choice=='Create new'", mandatory_depends_on: "eval:doc.choice=='Create new'"},
                {fieldname: 'product_slug', fieldtype: 'Data', label: __('Slug'), default: defaults.product_slug, description: __('Also the product’s record name and its web address.'), depends_on: "eval:doc.choice=='Create new'", mandatory_depends_on: "eval:doc.choice=='Create new'"},
                {fieldname: 'product_type', fieldtype: 'Select', label: __('Product Type'), options: defaults.product_types, default: defaults.product_type, hidden: single ? 1 : 0, depends_on: single ? '' : "eval:doc.choice=='Create new'"},
                {fieldname: 'product', fieldtype: 'Link', options: 'ilL-Webflow-Product', label: __('Existing Webflow Product'), depends_on: "eval:doc.choice=='Link existing'", mandatory_depends_on: "eval:doc.choice=='Link existing'",
                    get_query: () => ({filters: [[defaults.link_field, 'is', 'not set'], ['product_type', 'in', defaults.product_types]]})},
            ],
            primary_action_label: __('Continue'),
            primary_action(values) {
                dialog.disable_primary_action();
                const done = values.choice === 'Link existing'
                    ? link(frm, values.product, dialog)
                    : frappe.xcall(API + 'create_webflow_product', {
                        template_doctype: frm.doctype, template_id: frm.doc.name,
                        product_name: values.product_name, product_slug: values.product_slug, product_type: values.product_type,
                    }).then(product => link(frm, product, dialog).catch(error => {
                        frappe.msgprint(__('Webflow Product {0} was created but the template could not be saved, so they are not linked yet. Fix the problem shown, then choose Link existing and pick {0}.', [product]));
                        throw error;
                    }));
                done.catch(() => dialog.enable_primary_action());
            },
            secondary_action_label: __('Cancel'),
            secondary_action() { dialog.hide(); },
        });
        dialog.onhide = () => { if (!dialog.__done) revert(frm, previous); };
        dialog.show();
    }

    TEMPLATES.forEach(doctype => frappe.ui.form.on(doctype, {
        refresh(frm) { frm.__ill_status = frm.doc.product_status; },
        product_status(frm) {
            const previous = frm.__ill_status;
            if (frm.__ill_reverting) return;
            if (frm.doc.product_status !== LIVE || frm.doc.webflow_product) {
                frm.__ill_status = frm.doc.product_status;
                return;
            }
            if (frm.is_new()) {
                frappe.msgprint(__('Save the template first, then set it to Active + Live.'));
                revert(frm, previous);
                return;
            }
            frappe.xcall(API + 'go_live_defaults', {template_doctype: frm.doctype, template_id: frm.doc.name})
                .then(defaults => open(frm, previous, defaults))
                .catch(() => revert(frm, previous));
        },
    }));

    window.illGoLive = {open};
})();
