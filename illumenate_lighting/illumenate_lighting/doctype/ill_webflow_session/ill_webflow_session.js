// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Webflow-Session", {
    refresh(frm) {
        // Show expiry warning
        if (frm.doc.expires_at && new Date(frm.doc.expires_at) < new Date()) {
            frm.set_intro(__('This session has expired.'), 'red');
        } else if (frm.doc.status === 'Active') {
            frm.set_intro(__('Active session - expires: ') + frm.doc.expires_at, 'green');
        }
        
        // Add status-based styling
        if (frm.doc.status === 'Converted') {
            frm.set_intro(__('Session converted to project/order.'), 'blue');
        }
        
        // Add action buttons
        if (!frm.is_new() && frm.doc.status === 'Active') {
            frm.add_custom_button(__('Extend Expiry (+24h)'), function() {
                frappe.call({
                    method: 'run_doc_method',
                    args: {
                        dt: frm.doctype,
                        dn: frm.docname,
                        method: 'extend_expiry'
                    },
                    callback: function() {
                        frm.reload_doc();
                    }
                });
            }, __('Actions'));
            
            frm.add_custom_button(__('Mark Expired'), function() {
                frappe.call({
                    method: 'run_doc_method',
                    args: {
                        dt: frm.doctype,
                        dn: frm.docname,
                        method: 'mark_expired'
                    },
                    callback: function() {
                        frm.reload_doc();
                    }
                });
            }, __('Actions'));
        }
        
        // Show configuration preview
        if (frm.doc.configuration_json) {
            try {
                const config = JSON.parse(frm.doc.configuration_json);
                let html = '<table class="table table-bordered table-sm">';
                for (const [key, value] of Object.entries(config)) {
                    html += `<tr><td><strong>${frappe.unscrub(key)}</strong></td><td>${value}</td></tr>`;
                }
                html += '</table>';
                frm.set_df_property('configuration_json', 'description', html);
            } catch (e) {
                // JSON parsing failed, show raw
            }
        }
    },
    
    is_complex_fixture(frm) {
        // Show/hide portal redirect section based on complexity
        frm.toggle_display('portal_redirect_section', frm.doc.is_complex_fixture);
    }
});
