/* Duplicate as new product / template (hardening plan 5.3). Staff only; the server re-checks roles. */
(function () {
	const METHOD = "illumenate_lighting.illumenate_lighting.api.product_clone.duplicate";
	const PRODUCT = "ilL-Webflow-Product";
	const TEMPLATES = [
		"ilL-Fixture-Template", "ilL-Tape-Neon-Template", "ilL-LED-Sheet-Template",
		"ilL-Driver-Template", "ilL-Controller-Template", "ilL-Extrusion-Kit-Template",
	];
	const ROLES = ["System Manager", "ilL Catalog Publisher"];

	function slugify(text) {
		return String(text || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 120);
	}

	function fields(frm) {
		if (frm.doctype === PRODUCT) {
			return [
				{fieldname: "new_name", fieldtype: "Data", label: __("New product name"), reqd: 1,
					onchange() { const dialog = this.layout; dialog.set_value("new_slug", slugify(dialog.get_value("new_name"))); }},
				{fieldname: "new_slug", fieldtype: "Data", label: __("New slug"), reqd: 1,
					description: __("Lowercase letters, numbers and dashes. Webflow IDs and sync state are not copied.")},
				{fieldname: "template_code", fieldtype: "Data", label: __("Also copy the family template as (code)"),
					description: __("Leave blank to link a template later. A template belongs to one product, so the original's template is never shared.")},
				{fieldname: "include_media", fieldtype: "Check", label: __("Reuse images and documents (links the same files)"), default: 1},
			];
		}
		return [
			{fieldname: "new_name", fieldtype: "Data", label: __("New template code"), reqd: 1},
			{fieldname: "template_name", fieldtype: "Data", label: __("New template name")},
			{fieldname: "include_media", fieldtype: "Check", label: __("Reuse images and spec sheet (links the same files)"), default: 1},
		];
	}

	async function readiness(result) {
		const esc = frappe.utils.escape_html;
		const product = result.doctype === PRODUCT;
		const response = await frappe.call({
			method: "illumenate_lighting.illumenate_lighting.api.product_readiness." + (product ? "preview" : "authoring_preview"),
			args: product ? {product: result.name, channel: "portal"} : {doctype: result.doctype, name: result.name},
		});
		const report = response.message || {};
		const rows = (report.issues || []).map(row => `<li>${esc(row.record)} / ${esc(row.field)}: ${esc(row.message)}</li>`).join("");
		const warnings = (report.warnings || []).map(row => `<li class="text-warning">${esc(row.field)}: ${esc(row.message)}</li>`).join("");
		frappe.msgprint({
			title: __("Draft created: readiness"),
			wide: true,
			message: `<p>${esc(__("{0} was created as a draft.", [result.name]))}</p>` +
				(rows || warnings ? `<ul>${rows}${warnings}</ul>` : `<p>${esc(__("No readiness issues found."))}</p>`),
		});
	}

	function open(frm) {
		const dialog = new frappe.ui.Dialog({
			title: frm.doctype === PRODUCT ? __("Duplicate as new product") : __("Duplicate as new template"),
			fields: fields(frm),
			primary_action_label: __("Create draft"),
			async primary_action(values) {
				dialog.disable_primary_action();
				try {
					const response = await frappe.call({
						method: METHOD, type: "POST", freeze: true,
						args: {doctype: frm.doctype, name: frm.doc.name, ...values, include_media: values.include_media ? 1 : 0},
					});
					const result = response.message;
					dialog.hide();
					await frappe.set_route("Form", result.doctype, result.name);
					await readiness(result);
				} catch (error) {
					dialog.enable_primary_action();
				}
			},
		});
		if (frm.doctype === PRODUCT) dialog.set_value("new_name", __("{0} copy", [frm.doc.product_name || frm.doc.name]));
		dialog.show();
	}

	[PRODUCT, ...TEMPLATES].forEach(doctype => frappe.ui.form.on(doctype, {
		refresh(frm) {
			if (frm.is_new() || !frappe.user_roles.some(role => ROLES.includes(role))) return;
			frm.add_custom_button(__("Duplicate as new product"), () => {
				if (frm.is_dirty()) { frappe.msgprint(__("Save before duplicating.")); return; }
				open(frm);
			}, __("Actions"));
		},
	}));

	window.ProductClone = {slugify, fields, open};
})();
