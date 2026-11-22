// Stage pill beside the status on Sales Order and Quotation forms (api/order_stage.py).
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

	function show_stage(frm) {
		const head = frm.page && frm.page.indicator;
		if (head && head.siblings) head.siblings(".ill-stage-pill").remove();
		const stage = frm.doc.ill_stage;
		if (!stage || frm.is_new()) return;
		const color = ILL_STAGE_COLORS[frm.doctype][stage] || "gray";
		const detail = [
			frm.doc.ill_waiting_on ? __("Waiting on {0}", [__(frm.doc.ill_waiting_on)]) : "",
			frm.doc.ill_stage_note || "",
		].filter(Boolean).join(" · ");
		const pill = `<span class="indicator-pill ${color} ill-stage-pill" style="margin-left: 8px;" title="${esc(detail)}">`
			+ `${esc(__(stage))}${detail ? ` <span class="text-muted">· ${esc(detail)}</span>` : ""}</span>`;
		if (head && head.after) head.after(pill);
	}

	for (const doctype of Object.keys(ILL_STAGE_COLORS)) {
		frappe.ui.form.on(doctype, { refresh: show_stage });
	}
})();
