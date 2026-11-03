// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

const ILL_HERO_METHOD =
	"illumenate_lighting.illumenate_lighting.report.templates_without_hero_image.templates_without_hero_image.use_as_hero_image";

frappe.query_reports["Templates Without Hero Image"] = {
	filters: [
		{
			fieldname: "template_type",
			label: __("Template Type"),
			fieldtype: "Select",
			options: [
				"",
				"ilL-Fixture-Template",
				"ilL-Tape-Neon-Template",
				"ilL-LED-Sheet-Template",
				"ilL-Extrusion-Kit-Template",
				"ilL-Driver-Template",
				"ilL-Controller-Template",
			],
		},
		{
			fieldname: "only_with_suggestion",
			label: __("Only templates with an image to use"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "include_inactive",
			label: __("Include inactive templates"),
			fieldtype: "Check",
			default: 0,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		const escape = frappe.utils.escape_html;
		if (column.fieldname === "suggested_image" && data && data.suggested_image) {
			return '<a href="' + escape(data.suggested_image) + '" target="_blank" rel="noopener">'
				+ '<img src="' + escape(data.suggested_image) + '" alt="" style="max-height:32px;max-width:100px"></a>';
		}
		if (column.fieldname === "action" && data && data.suggested_image) {
			if (!data.suggestion_public) return escape(__("Image is not public"));
			if (!data.can_use) return "";
			return '<button type="button" class="btn btn-xs btn-default ill-use-hero"'
				+ ' data-template-type="' + escape(data.template_type) + '"'
				+ ' data-template="' + escape(data.template) + '"'
				+ ' data-image="' + escape(data.suggested_image) + '">'
				+ escape(__("Use as hero image")) + "</button>";
		}
		return default_formatter(value, row, column, data);
	},

	onload(report) {
		report.page.wrapper.on("click", ".ill-use-hero", function () {
			const button = this;
			const args = {
				template_type: button.getAttribute("data-template-type"),
				template: button.getAttribute("data-template"),
				image: button.getAttribute("data-image"),
			};
			frappe.confirm(
				__("Make this image the main product image of {0}? Dealers and Webflow will show it.", [frappe.utils.escape_html(args.template)]),
				() => {
					button.disabled = true;
					frappe.call({ method: ILL_HERO_METHOD, type: "POST", args, freeze: true })
						.then(() => {
							frappe.show_alert({ message: __("Hero image set"), indicator: "green" });
							report.refresh();
						})
						.catch(() => { button.disabled = false; });
				}
			);
		});
	},
};
