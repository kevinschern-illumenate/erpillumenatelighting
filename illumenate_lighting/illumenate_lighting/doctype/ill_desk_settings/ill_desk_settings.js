// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Desk-Settings", {
	refresh(frm) {
		const slug = frm.doc.slug;
		if (!slug || frm.is_dirty() || frappe.session.user !== frm.doc.desk_owner) return;
		const url = `/kd/${encodeURIComponent(slug)}`;
		frm.add_custom_button(__("Open my desk"), () => window.open(url, "_blank", "noopener"));
		frm.set_intro(__("Your desk: {0}", [`<a href="${url}" target="_blank" rel="noopener">${location.origin}${url}</a>`]), "blue");
	},
});
