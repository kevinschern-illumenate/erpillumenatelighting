// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Finder-Question", {
	onload(frm) {
		frappe.call("illumenate_lighting.illumenate_lighting.portal.product_finder.desk.facet_registry").then((r) => {
			frm.__facets = r.message || {};
			apply_facet(frm);
		});
	},

	refresh(frm) {
		frm.add_custom_button(__("Preview"), () => preview_question(frm));
		apply_facet(frm);
	},

	facet(frm) {
		apply_facet(frm);
	},
});

// Limit ERP Attribute Type and Comparison to what the chosen product fact supports.
function apply_facet(frm) {
	const spec = (frm.__facets || {})[frm.doc.facet];
	if (!spec) return;
	frm.fields_dict.value_maps.grid.update_docfield_property("attribute_doctype", "options", ["", ...spec.doctypes].join("\n"));
	frm.set_df_property("comparison", "options", ["", ...spec.comparisons].join("\n"));
	frm.set_df_property(
		"value_maps",
		"description",
		spec.derived
			? __("{0} is read from product data; no ERP mapping is needed.", [spec.label])
			: spec.doctypes.length
				? __("Map each answer to the {0} records it means.", [spec.doctypes.join(", ")])
				: __("{0} is compared using the option numbers; no ERP mapping is needed.", [spec.label])
	);
}

// Render the question roughly as dealers will see it, from the unsaved form values.
function preview_question(frm) {
	const esc = frappe.utils.escape_html;
	const options = (frm.doc.options || []).filter((row) => row.is_active);
	const cards = options
		.map((row) => {
			const visual = row.image
				? `<img src="${esc(row.image)}" alt="" style="width:100%;height:110px;object-fit:cover;border-radius:6px">`
				: `<div style="height:110px;border-radius:6px;background:${esc(row.swatch_color || "#f3f3f3")}"></div>`;
			const badge = row.badge_text ? `<span class="indicator-pill blue">${esc(row.badge_text)}</span>` : "";
			const featured = row.is_featured ? "grid-column:span 2;border:2px solid var(--primary)" : "border:1px solid var(--border-color)";
			return `<div style="${featured};border-radius:8px;padding:8px">${visual}
				<div style="margin-top:6px;font-weight:600">${esc(row.label || row.value || "")}</div>
				${badge}<div class="text-muted small">${esc(row.description || "")}</div>
				${row.note ? `<div class="text-warning small">${esc(row.note)}</div>` : ""}
				${row.is_no_preference ? `<div class="text-muted small">${__("Does not filter products")}</div>` : ""}</div>`;
		})
		.join("");
	const number = ["Number", "Range"].includes(frm.doc.question_type)
		? `<p class="text-muted">${__("Number input")}: ${esc(String(frm.doc.number_min ?? ""))} – ${esc(String(frm.doc.number_max ?? ""))} ${esc(frm.doc.unit || "")}</p>`
		: "";
	const dialog = new frappe.ui.Dialog({
		title: __("Preview: {0}", [frm.doc.short_label || frm.doc.label || ""]),
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "body" }],
	});
	dialog.fields_dict.body.$wrapper.html(`
		<h4>${esc(frm.doc.label || "")}</h4>
		${frm.doc.tooltip ? `<p class="text-muted">${esc(frm.doc.tooltip)}</p>` : ""}
		${number}
		<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">${cards}</div>
		${frm.doc.is_active ? "" : `<p class="text-warning" style="margin-top:10px">${__("Inactive: dealers do not see this question.")}</p>`}
	`);
	dialog.show();
}
