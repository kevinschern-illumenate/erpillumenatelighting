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

function showTemplateName(frm) {
    // Order (owner, 2026-11-04): brand pill, record name (KIT-RA04), Template Name, stacked.
    // One block at the top of the sidebar, placed the way the Webflow Product places its
    // Target Brands pill, outside the title row with the print and like icons.
    const $side = $(frm.page.wrapper).find('.layout-side-section').first();
    if (!$side.length) return;
    $side.find('.ill-template-header').remove();
    if (frm.is_new()) return;

    const $block = $('<div class="ill-template-header"></div>')
        .css({display: 'block', padding: '0 15px', 'margin-top': '10px', 'margin-bottom': '-10px'});

    const brands = (frm.doc.target_brands || []).filter(row => row.enabled && row.brand);
    if (brands.length) {
        const $pills = $('<div></div>').css({'margin-bottom': '6px'});
        brands.forEach(row => {
            const pill = BRAND_PILLS[row.brand] || {label: row.brand, background: '#8d99a6', color: 'white'};
            $('<span class="badge"></span>').text(pill.label).css({
                'background-color': pill.background, color: pill.color, 'font-weight': 500, 'margin-right': '5px',
            }).appendTo($pills);
        });
        $block.append($pills);
    }
    $('<div></div>').text(frm.doc.name).css({'font-weight': 600, 'word-break': 'break-word'}).appendTo($block);
    if (frm.doc.template_name) {
        $('<div class="text-muted"></div>').text(frm.doc.template_name)
            .css({'word-break': 'break-word', 'margin-top': '2px'}).appendTo($block);
    }
    $side.prepend($block);
    hideTitleText(frm, $side);
}

function hideTitleText(frm, $side) {
    // Hide the record title in Frappe's title row (the print and like icons stay): the block
    // above already shows the Template Name (owner, 2026-11-04).
    const titles = [frm.doc.template_name, frm.get_title && frm.get_title()]
        .filter(Boolean).map(t => String(t).trim());
    if (!titles.length) return;
    $side.find('*').not('.ill-template-header, .ill-template-header *').filter(function () {
        return this.children.length === 0 && titles.includes($(this).text().trim());
    }).first().hide();
}
