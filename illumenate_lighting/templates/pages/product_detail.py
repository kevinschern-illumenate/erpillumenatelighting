# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Product Detail Page Handler

Renders the /portal/products/<slug> page (System Manager only).
"""

import frappe
from frappe import _

no_cache = 1


def get_context(context):
    """Build context for the product detail page."""
    if frappe.session.user == "Guest":
        frappe.throw(_("Please log in to access the product catalog"), frappe.PermissionError)

    frappe.only_for("System Manager")

    product_slug = frappe.form_dict.get("slug", "")

    # Validate product exists
    if not product_slug or not frappe.db.exists(
        "ilL-Webflow-Product", {"product_slug": product_slug}
    ):
        frappe.throw(_("Product not found"), frappe.DoesNotExistError)

    product = frappe.get_doc("ilL-Webflow-Product", {"product_slug": product_slug})

    context.product_slug = product_slug
    context.product_name = product.product_name
    context.is_configurable = bool(product.is_configurable)
    context.fixture_template = product.fixture_template or ""
    context.title = product.product_name or _("Product Detail")
    context.no_cache = 1
    return context
