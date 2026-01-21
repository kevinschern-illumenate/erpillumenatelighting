// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Attribute-Feed-Direction", {
    refresh(frm) {
        // Add any custom refresh logic here
    },
    
    code(frm) {
        // Auto-uppercase the code
        if (frm.doc.code) {
            frm.set_value('code', frm.doc.code.toUpperCase());
        }
    }
});
