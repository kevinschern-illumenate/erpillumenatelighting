// "Open in portal" on Desk forms whose record a dealer can open: staff see what the buyer sees.
(function () {
	const enc = encodeURIComponent;
	const ROUTES = {
		'ilL-Project': doc => '/portal/projects/' + enc(doc.name),
		'ilL-Project-Fixture-Schedule': doc => '/portal/schedules/' + enc(doc.name),
		'ilL-Quote-Request': doc => '/portal/quote-requests/' + enc(doc.name),
		'ilL-Quote-Offer': doc => '/portal/quotes/' + enc(doc.name),
		'ilL-Order-Intake': doc => doc.sales_order ? '/portal/orders/' + enc(doc.sales_order) : null,
		'ilL-Document-Request': doc => '/portal/drawings/' + enc(doc.name),
		'Issue': doc => doc.ill_portal_request_key ? '/portal/support/' + enc(doc.name) : null,
		'Sales Order': doc => doc.ill_fixture_schedule ? '/portal/orders/' + enc(doc.name) : null,
	};
	window.illumenate_portal_path = (doctype, doc) => (ROUTES[doctype] ? ROUTES[doctype](doc) : null);
	Object.keys(ROUTES).forEach(doctype => frappe.ui.form.on(doctype, {
		refresh(frm) {
			if (frm.is_new()) return;
			const path = window.illumenate_portal_path(doctype, frm.doc);
			if (path) frm.add_custom_button(__('Open in portal'), () => window.open(path, '_blank', 'noopener'));
		}
	}));
})();
