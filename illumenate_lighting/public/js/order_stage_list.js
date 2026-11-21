// Stage column on the Sales Order and Quotation lists (api/order_stage.py).
// Loaded after ERPNext's own list settings, so it adds to them instead of replacing them.
// Colours must match STAGES in api/order_stage.py (tests/portal_unit/test_order_stage.py checks).
(() => {
	const ILL_STAGE_COLORS = {
		"Sales Order": {
			"Pending Approval": "gray",
			"Hold for Release": "purple",
			"Hold for Confirmation": "purple",
			"Needs Work Orders": "red",
			"Pend-Prod": "blue",
			"Waiting for parts": "orange",
			"In-Prod": "green",
			"Paint": "orange",
			"Held": "red",
			"Pend-Ship": "green",
			"Hold for Ship": "purple",
			"Will Call - Ready": "green",
			"Proforma - Awaiting Payment": "yellow",
			"Partially Shipped": "light-blue",
			"Shipped / In Transit": "cyan",
			"Delivered": "darkgrey",
			"Completed": "gray",
			"Cancelled": "red",
		},
		"Quotation": {
			"Drafting": "gray",
			"Waiting on Info": "orange",
			"Waiting on Vendor": "orange",
			"Sent": "blue",
			"Revising": "purple",
			"Follow Up": "red",
			"Won": "green",
			"Lost": "darkgrey",
			"Expired": "gray",
			"Cancelled": "red",
		},
	};
	const esc = (value) => frappe.utils.escape_html(String(value || ""));

	for (const doctype of Object.keys(ILL_STAGE_COLORS)) {
		const settings = (frappe.listview_settings[doctype] = frappe.listview_settings[doctype] || {});
		settings.add_fields = [...new Set([...(settings.add_fields || []), "ill_stage", "ill_waiting_on", "ill_stage_note"])];
		settings.formatters = Object.assign({}, settings.formatters, {
			ill_stage(value, _df, doc) {
				if (!value) return "";
				const color = ILL_STAGE_COLORS[doctype][value] || "gray";
				const title = [doc.ill_waiting_on ? __("Waiting on {0}", [__(doc.ill_waiting_on)]) : "", doc.ill_stage_note || ""]
					.filter(Boolean)
					.join(" · ");
				return `<span class="indicator-pill ${color} ellipsis" title="${esc(title)}">${esc(__(value))}</span>`;
			},
		});
	}
})();
