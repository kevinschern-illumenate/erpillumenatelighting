"""One route contract for portal and Desk links (hardening plan 7.1).

``PORTAL_ROUTES`` is the only place that spells portal addresses for records. Python callers
use ``portal_path``; Desk scripts read the same table from ``frappe.boot.ill_portal_routes``
and portal pages from the ``#ill-portal-routes`` JSON block in ``portal_base.html``.
``tests/portal_unit/test_route_inventory.py`` checks every template resolves to a page.
"""

from urllib.parse import quote, unquote

PORTAL_ROUTES = {
	"account": "/portal/account",
	"collaborators": "/portal/projects/{name}/collaborators",
	"drawing": "/portal/drawings/{name}",
	"order": "/portal/orders/{name}",
	"product_verification": "/portal/product-verification/{name}",
	"project": "/portal/projects/{name}",
	"quote": "/portal/quotes/{name}",
	"quote_request": "/portal/quote-requests/{name}",
	"schedule": "/portal/schedules/{name}",
	"support": "/portal/support/{name}",
}

# The Desk record behind each record page, used for the staff "Open in Desk" link.
ROUTE_DOCTYPES = {
	"drawing": "ilL-Document-Request",
	"order": "Sales Order",
	"product_verification": "ilL-Product-Verification-Request",
	"project": "ilL-Project",
	"quote": "ilL-Quote-Offer",
	"quote_request": "ilL-Quote-Request",
	"schedule": "ilL-Project-Fixture-Schedule",
	"support": "Issue",
}


def portal_path(key, name=None):
	"""The portal address for ``key``; ``name`` is URL-encoded as one path segment."""
	template = PORTAL_ROUTES[key]
	if "{name}" not in template:
		return template
	if not name:
		raise ValueError(f"portal route {key!r} needs a record name")
	return template.replace("{name}", quote(str(name), safe=""))


def desk_path(doctype, name):
	"""``/app/<doctype-slug>/<name>``, the same slug Frappe's router uses."""
	slug = doctype.lower().replace(" ", "-")
	return f"/app/{quote(slug, safe='-')}/{quote(str(name), safe='')}"


def record_for_path(path):
	"""``(doctype, name)`` for a portal record page or anything under it, else ``None``."""
	parts = [part for part in (path or "").split("?")[0].split("/") if part]
	if len(parts) < 3 or parts[0] != "portal":
		return None
	for key, doctype in ROUTE_DOCTYPES.items():
		template = [part for part in PORTAL_ROUTES[key].split("/") if part]
		if len(template) == 3 and template[1] == parts[1] and template[2] == "{name}":
			return doctype, unquote(parts[2])
	return None


def extend_bootinfo(bootinfo):
	bootinfo.ill_portal_routes = dict(PORTAL_ROUTES)
	bootinfo.ill_portal_route_doctypes = dict(ROUTE_DOCTYPES)
