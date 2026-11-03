/* One route contract (hardening plan 7.1). The table comes from the server: portal/routes.py
 * PORTAL_ROUTES, through frappe.boot in Desk and the #ill-portal-routes JSON block on portal
 * pages. DEFAULTS is only a fallback for a stale boot; a unit test keeps it equal to the server. */
(function (root) {
	'use strict';
	const DEFAULTS = {
		account: '/portal/account',
		collaborators: '/portal/projects/{name}/collaborators',
		drawing: '/portal/drawings/{name}',
		order: '/portal/orders/{name}',
		product_verification: '/portal/product-verification/{name}',
		project: '/portal/projects/{name}',
		quote: '/portal/quotes/{name}',
		quote_request: '/portal/quote-requests/{name}',
		schedule: '/portal/schedules/{name}',
		support: '/portal/support/{name}',
	};

	function table() {
		const boot = root.frappe && root.frappe.boot && root.frappe.boot.ill_portal_routes;
		if (boot) return boot;
		const block = root.document && root.document.getElementById('ill-portal-routes');
		if (block) {
			try { return JSON.parse(block.textContent); } catch (e) { /* fall back */ }
		}
		return DEFAULTS;
	}

	function path(key, name) {
		const template = table()[key] || DEFAULTS[key];
		if (!template) return null;
		if (template.indexOf('{name}') === -1) return template;
		if (name === undefined || name === null || name === '') return null;
		return template.replace('{name}', encodeURIComponent(String(name)));
	}

	root.PortalRoutes = { DEFAULTS: DEFAULTS, table: table, path: path };
})(typeof window !== 'undefined' ? window : globalThis);
