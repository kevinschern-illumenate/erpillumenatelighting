# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Product Catalog Page Handler

Renders the /portal/products page (System Manager only).
"""

import frappe
from frappe import _

no_cache = 1


def get_context(context):
    """Build context for the product catalog page."""
    if frappe.session.user == "Guest":
        frappe.throw(_("Please log in to access the product catalog"), frappe.PermissionError)

    frappe.only_for("System Manager")

    context.title = _("Product Catalog")
    context.no_cache = 1
    return context
