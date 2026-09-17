# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Product Catalog Page Handler

Renders the /portal/products page for Dealers and internal users.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.access import require_catalog_access

no_cache = 1


def get_context(context):
    """Build context for the product catalog page."""
    if frappe.session.user == "Guest":
        frappe.throw(_("Please log in to access the product catalog"), frappe.PermissionError)

    require_catalog_access()

    context.title = _("Product Catalog")
    context.no_cache = 1
    return context
