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
from illumenate_lighting.illumenate_lighting.portal.web_guard import require_login
from illumenate_lighting.illumenate_lighting.portal_listing import portal_product

no_cache = 1


def get_context(context):
    """Build context for the product detail page."""
    require_login()

    if not can_view_catalog():
        frappe.local.flags.redirect_location = "/portal/request-dealer-access"
        raise frappe.Redirect

    product_slug = frappe.form_dict.get("slug", "")

    # Validate the product exists and the portal shows it
    product = portal_product({"product_slug": product_slug}) if product_slug else None
    if not product:
        frappe.throw(_("Product not found"), frappe.DoesNotExistError)

    context.product_slug = product_slug
    context.product_name = product.product_name
    context.is_staff = allowed("sales") or allowed("engineering")
    context.product_desk_url = f"/app/ill-webflow-product/{quote(product.name, safe='')}"
    context.title = product.product_name or _("Product Detail")
    context.no_cache = 1
    return context
