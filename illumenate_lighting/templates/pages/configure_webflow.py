# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Configure Page (Webflow-Compatible)

Handles the /portal/configure_webflow page that follows the 
Webflow configurator step order.
"""

import frappe
from frappe import _


def get_context(context):
    """Build page context for the Webflow-compatible configurator."""
    
    # Check if user is logged in
    if frappe.session.user == "Guest":
        frappe.throw(_("Please log in to configure fixtures"), frappe.PermissionError)
    
    # Get URL parameters
    schedule_name = frappe.form_dict.get("schedule")
    product_slug = frappe.form_dict.get("product")
    session_id = frappe.form_dict.get("session_id")
    template_code = frappe.form_dict.get("template")
    
    # Get schedule if provided
    schedule = None
    can_save = False
    if schedule_name and frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
        schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)
        can_save = schedule.has_permission("write")
    
    # Get available templates
    templates = frappe.get_all(
        "ilL-Fixture-Template",
        filters={"is_active": 1},
        fields=["template_code", "template_name"],
        order_by="template_name"
    )
    
    # If product_slug is provided, get the associated template
    selected_template = template_code
    if product_slug:
        product_template = frappe.db.get_value(
            "ilL-Webflow-Product",
            {"product_slug": product_slug},
            "fixture_template"
        )
        if product_template:
            selected_template = product_template
    
    # If session_id is provided, load session data
    session_data = None
    if session_id and frappe.db.exists("ilL-Webflow-Session", session_id):
        session = frappe.get_doc("ilL-Webflow-Session", session_id)
        if not session.is_expired():
            session_data = session.get_configuration()
            if session.product_slug:
                product_slug = session.product_slug
    
    # Check if pricing should be shown
    show_pricing = _should_show_pricing()
    
    context.update({
        "schedule": schedule,
        "templates": templates,
        "selected_template": selected_template,
        "product_slug": product_slug,
        "session_id": session_id,
        "session_data": session_data,
        "can_save": can_save,
        "show_pricing": show_pricing,
        "no_cache": 1
    })
    
    return context


def _should_show_pricing() -> bool:
    """Determine if pricing should be shown to the current user."""
    user = frappe.session.user
    
    # Always show for System Manager
    if "System Manager" in frappe.get_roles(user):
        return True
    
    # Check for pricing role
    if "Dealer" in frappe.get_roles(user):
        return True
    
    # Check user settings
    # (Could add a user preference here)
    
    return False
