/* Template form extras (owner, 2026-11-04):
   - the brand pill, the record name and the Template Name at the top of the sidebar;
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

// Brand names and colours as on the Webflow Product's sidebar pill.
const BRAND_PILLS = {
    illumenate: {label: 'ilLumenate Lighting', background: '#0052cc', color: 'white'},
    lighting_206: {label: '206 Lighting', background: '#fdc757', color: '#172e48'},
};

function titleRow($sidebar, name) {
    // The element showing the record name (for example KIT-RA04), then the whole row holding
    // it with the print and like icons. The pill goes above that row and the Template Name
    // below it, so the three stack vertically and the record name keeps its space.
    const $text = $sidebar.find('*').filter(function () {
        return this.children.length === 0 && $(this).text().trim() === name;
    }).first();
    if (!$text.length) return null;
    let $row = $text;
    while ($row.parent().length && !$row.parent().is($sidebar)) {
        $row = $row.parent();
        if ($row.find('svg, button, .icon').length) break;
    }
    return $row;
}

function showTemplateName(frm) {
    // Order (owner, 2026-11-04): brand pill, record name (KIT-RA04), Template Name.
    const $sidebar = frm.sidebar && frm.sidebar.sidebar;
    if (!$sidebar) return;
    $sidebar.find('.ill-template-name, .ill-template-brand').remove();
    if (frm.is_new()) return;
    const $row = titleRow($sidebar, frm.doc.name);

    const brands = (frm.doc.target_brands || []).filter(row => row.enabled && row.brand);
    if (brands.length) {
        const $pills = $('<div class="ill-template-brand"></div>').css({display: 'block', width: '100%', padding: '0 0 6px'});
        brands.forEach(row => {
            const pill = BRAND_PILLS[row.brand] || {label: row.brand, background: '#8d99a6', color: 'white'};
            $('<span class="badge"></span>').text(pill.label).css({
                'background-color': pill.background, color: pill.color, 'font-weight': 500, 'margin-right': '5px',
            }).appendTo($pills);
        });
        if ($row) {
            $pills.insertBefore($row);
        } else {
            $sidebar.prepend($pills);
        }
    }

    const name = frm.doc.template_name;
    if (!name) return;
    const $name = $('<div class="ill-template-name text-muted"></div>')
        .text(name)
        .css({display: 'block', width: '100%', 'word-break': 'break-word', 'margin-top': '2px'});
    if ($row) {
        $name.insertAfter($row);
    } else {
        $sidebar.prepend($name);
    }
}
