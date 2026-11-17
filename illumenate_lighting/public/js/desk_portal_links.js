// "Open in portal" on Desk forms whose record a dealer can open: staff see what the buyer sees.
// Addresses come from the one route contract (portal/routes.py via PortalRoutes, plan 7.1).
// A record the dealer cannot open yet gets a dimmed button that explains why (plan 7.2).
(function () {
	const t = (text) => (typeof __ === 'function' ? __(text) : text);
	const route = (key, name) => window.PortalRoutes.path(key, name);
	const blocked = reason => ({ reason: t(reason) });
	const NO_ORDER = 'Dealers see this in the portal once a Sales Order is linked.';
	const MESSAGE_KEYS = {
		'ilL-Document-Request': 'drawing',
		'ilL-Product-Verification-Request': 'product_verification',
		'ilL-Quote-Request': 'quote_request',
		'Issue': 'support',
	};
	const salesOrderOf = (doctype, name) => frappe.db.get_value(doctype, name, 'sales_order')
		.then(r => ((r && r.message) || {}).sales_order);

	function messageTarget(doc) {
		const key = MESSAGE_KEYS[doc.reference_type];
		if (key) return doc.reference_name ? route(key, doc.reference_name) : null;
		if (['ilL-Order-Intake', 'ilL-Order-Change'].includes(doc.reference_type) && doc.reference_name) {
			return salesOrderOf(doc.reference_type, doc.reference_name)
				.then(order => (order ? route('order', order) : blocked(NO_ORDER)));
		}
		return null;
	}

	const TARGETS = {
		'ilL-Project': doc => route('project', doc.name),
		'ilL-Project-Fixture-Schedule': doc => route('schedule', doc.name),
		'ilL-Quote-Request': doc => route('quote_request', doc.name),
		'ilL-Quote-Offer': doc => route('quote', doc.name),
		'ilL-Order-Intake': doc => (doc.sales_order ? route('order', doc.sales_order) : null),
		'ilL-Document-Request': doc => route('drawing', doc.name),
		'Issue': doc => (doc.ill_portal_request_key ? route('support', doc.name) : null),
		'Sales Order': doc => (doc.ill_fixture_schedule
			? route('order', doc.name)
			: blocked('This Sales Order has no fixture schedule, so dealers do not see it in the portal.')),
		'ilL-Order-Change': doc => (doc.sales_order ? route('order', doc.sales_order) : blocked(NO_ORDER)),
		'ilL-Drawing-Review': doc => (doc.request ? route('drawing', doc.request) : null),
		'ilL-Account-Request': () => route('account'),
		'ilL-Portal-Invitation': doc => (doc.project ? route('collaborators', doc.project) : route('account')),
		'ilL-Portal-Message': messageTarget,
	};

	// Kept for callers of the old helper: the path, or null when there is none.
	window.illumenate_portal_path = (doctype, doc) => {
		const target = TARGETS[doctype] ? TARGETS[doctype](doc) : null;
		return typeof target === 'string' ? target : null;
	};

	function addButton(frm, target) {
		if (!target) return;
		if (typeof target === 'string') {
			frm.add_custom_button(t('Open in portal'), () => window.open(target, '_blank', 'noopener'));
			return;
		}
		const reason = target.reason;
		const $button = frm.add_custom_button(t('Open in portal'), () => frappe.msgprint(reason));
		if ($button && $button.attr) $button.attr({ 'aria-disabled': 'true', title: reason }).css('opacity', 0.65);
	}

	Object.keys(TARGETS).forEach(doctype => frappe.ui.form.on(doctype, {
		refresh(frm) {
			if (frm.is_new()) return;
			const target = TARGETS[doctype](frm.doc);
			if (target && typeof target.then === 'function') {
				const name = frm.doc.name;
				target.then(result => { if (frm.doc.name === name) addButton(frm, result); });
			} else addButton(frm, target);
		}
	}));
})();
