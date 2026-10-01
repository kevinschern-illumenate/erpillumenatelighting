# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Product Detail Page Handler

Renders the /portal/products/<slug> page for Dealers and internal users.
"""

from urllib.parse import quote

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.access import can_view_catalog
from illumenate_lighting.illumenate_lighting.portal.staff import allowed

no_cache = 1


def get_context(context):
    """Build context for the product detail page."""
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

    product_slug = frappe.form_dict.get("slug", "")

    # Validate product exists
    if not product_slug or not frappe.db.exists(
        "ilL-Webflow-Product", {"product_slug": product_slug, "is_active": 1}
    ):
        frappe.throw(_("Product not found"), frappe.DoesNotExistError)

    product = frappe.get_doc("ilL-Webflow-Product", {"product_slug": product_slug})

    context.product_slug = product_slug
    context.product_name = product.product_name
    context.is_staff = allowed("sales") or allowed("engineering")
    context.product_desk_url = f"/app/ill-webflow-product/{quote(product.name, safe='')}"
    context.title = product.product_name or _("Product Detail")
    context.no_cache = 1
    return context
