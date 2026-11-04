/* Template form extras (owner, 2026-11-04):
   - the Template Name under the record name in the sidebar;
   - Actions > Apply Calculations, which recalculates the saved template (specifications,
     configurator, component and badge images) and saves its Webflow Product. */
['ilL-Fixture-Template', 'ilL-Tape-Neon-Template', 'ilL-LED-Sheet-Template', 'ilL-Driver-Template',
    'ilL-Controller-Template', 'ilL-Extrusion-Kit-Template'].forEach(doctype => {
    frappe.ui.form.on(doctype, {
        refresh(frm) {
            showTemplateName(frm);
            if (frm.is_new()) return;
            frm.add_custom_button(__('Apply Calculations'), () => {
                if (frm.is_dirty()) {
                    frappe.msgprint(__('Save the template first.'));
                    return;
                }
                frappe.call({
                    method: 'illumenate_lighting.illumenate_lighting.template_listing.apply_calculations',
                    args: {template_doctype: frm.doctype, template_id: frm.doc.name},
                    freeze: true,
                    freeze_message: __('Applying calculations...'),
                }).then(r => {
                    if (!r || r.exc) return;
                    frappe.show_alert({message: __('Calculations applied.'), indicator: 'green'});
                    frm.reload_doc();
                });
            }, __('Actions'));
        },
        template_name(frm) {
            showTemplateName(frm);
        },
    });
});

function showTemplateName(frm) {
    const $sidebar = frm.sidebar && frm.sidebar.sidebar;
    if (!$sidebar) return;
    $sidebar.find('.ill-template-name').remove();
    const name = frm.doc.template_name;
    if (!name || frm.is_new()) return;
    const $el = $('<div class="ill-template-name text-muted small"></div>')
        .text(name)
        .css({padding: '0 var(--padding-sm, 8px) var(--padding-sm, 8px)', 'word-break': 'break-word'});
    // Right under the record name at the top of the sidebar.
    const $title = $sidebar.find('.sidebar-meta-details, .sidebar-image-section, .form-sidebar-title').first();
    if ($title.length) {
        $el.insertAfter($title);
    } else {
        $sidebar.prepend($el);
    }
}
