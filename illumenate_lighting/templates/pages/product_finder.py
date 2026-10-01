"""Authenticated Finder entry point, including delayed public-session claims."""

from urllib.parse import urlencode

import frappe
from frappe.utils import cint, quote

no_cache = 1


def get_context(context):
	from illumenate_lighting.illumenate_lighting.portal.access import can_view_catalog
	from illumenate_lighting.illumenate_lighting.portal.product_finder import sessions
	from illumenate_lighting.illumenate_lighting.portal.product_finder.content import SETTINGS
	from illumenate_lighting.illumenate_lighting.portal.product_finder.desk import can_edit_content

	claim = frappe.form_dict.get("claim")
	if frappe.session.user == "Guest":
		query = frappe.request.query_string
		url = frappe.request.path + (
			"?" + (query.decode() if isinstance(query, bytes) else query) if query else ""
		)
		frappe.local.flags.redirect_location = "/login?redirect-to=" + quote(url, safe="")
		raise frappe.Redirect
	if not can_view_catalog():
		frappe.local.flags.redirect_location = "/portal/request-dealer-access" + (
			"?" + urlencode({"claim": claim}) if claim else ""
		)
		raise frappe.Redirect
	preview = bool(cint(frappe.form_dict.get("preview")) and can_edit_content())
	if not frappe.db.get_single_value(SETTINGS, "portal_enabled") and not preview:
		frappe.local.flags.redirect_location = "/portal/products"
		raise frappe.Redirect
	token = frappe.form_dict.get("session")
	if token:
		sessions.get_owned(token)
	context.update(
		{
			"title": "Product Finder",
			"no_cache": 1,
			"session_token": token,
			"claim_token": claim,
			"preview": preview,
			"csrf_token": frappe.sessions.get_csrf_token(),
		}
	)
	return context
