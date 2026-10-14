# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Product Catalog Page Handler

Renders the /portal/products page for Dealers and internal users.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.access import can_view_catalog
from illumenate_lighting.illumenate_lighting.portal.web_guard import require_login

no_cache = 1


def get_context(context):
    """Build context for the product catalog page."""
    require_login()

    if not can_view_catalog():
        frappe.local.flags.redirect_location = "/portal/request-dealer-access"
        raise frappe.Redirect

    context.title = _("Product Catalog")
    context.no_cache = 1
    return context
