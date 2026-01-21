// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Webflow-Configurator-Cache", {
    refresh(frm) {
        // Check if expired
        if (frm.doc.expires_at && new Date(frm.doc.expires_at) < new Date()) {
            frm.set_intro(__('This cache entry has expired.'), 'red');
        }
        
        // Add button to invalidate cache
        if (!frm.is_new()) {
            frm.add_custom_button(__('Invalidate'), function() {
                frm.set_value('is_valid', 0);
                frm.save();
            }, __('Actions'));
        }
    }
});
