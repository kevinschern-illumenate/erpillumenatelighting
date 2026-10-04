# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Product Catalog Page Handler

Renders the /portal/products page for Dealers and internal users.
"""

import frappe
from frappe import _
from frappe.utils import quote

from illumenate_lighting.illumenate_lighting.portal.access import can_view_catalog

no_cache = 1


def get_context(context):
    """Build context for the product catalog page."""
    if frappe.session.user == "Guest":
        current_url = frappe.utils.get_url(frappe.request.path)
        if frappe.request.query_string:
            query = frappe.request.query_string
            current_url += f"?{query.decode('utf-8') if isinstance(query, bytes) else query}"
        frappe.local.flags.redirect_location = f"/login?redirect-to={quote(current_url, safe='')}"
        raise frappe.Redirect

    if not can_view_catalog():
        frappe.local.flags.redirect_location = "/portal/request-dealer-access"
        raise frappe.Redirect

    context.title = _("Product Catalog")
    context.no_cache = 1
    return context
