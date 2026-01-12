# Copyright (c) 2024, Illumenate Lighting
# For license information, please see license.txt

import frappe
from frappe import _


def get_context(context):
    """Context for Multi-Segment Fixture Configurator portal page."""
    
    # Check if user is logged in
    if frappe.session.user == "Guest":
        frappe.throw(_("Please login to access this page"), frappe.PermissionError)
    
    # Get schedule if passed as query param
    schedule_name = frappe.form_dict.get("schedule")
    line_idx = frappe.form_dict.get("line_idx")
    
    context.schedule = None
    context.line_idx = line_idx
    context.can_save = False
    context.show_pricing = False
    
    if schedule_name:
        # Validate access to the schedule
        try:
            schedule = frappe.get_doc("ilL-Lighting-Schedule", schedule_name)
            
            # Check if user has access to the project
            project = frappe.get_doc("ilL-Lighting-Project", schedule.lighting_project)
            
            # User must be the project owner or in allowed contacts
            user = frappe.session.user
            user_email = frappe.get_value("User", user, "email")
            
            has_access = False
            if project.owner == user:
                has_access = True
            else:
                # Check if user is in allowed project contacts
                for contact in project.get("allowed_contacts", []):
                    if contact.user == user or contact.email == user_email:
                        has_access = True
                        break
            
            if not has_access:
                frappe.throw(_("You do not have access to this schedule"), frappe.PermissionError)
            
            context.schedule = schedule
            context.can_save = True
            
            # Show pricing based on project settings or user role
            if project.get("show_pricing") or "Sales Manager" in frappe.get_roles():
                context.show_pricing = True
                
        except frappe.DoesNotExistError:
            frappe.throw(_("Schedule not found"), frappe.DoesNotExistError)
    
    # Load available fixture templates
    templates = frappe.get_all(
        "ilL-Fixture-Template",
        filters={"is_active": 1, "allow_multisegment": 1},
        fields=["name", "template_code", "template_name"],
        order_by="template_name"
    )
    
    # If no templates with allow_multisegment flag, fall back to all active templates
    if not templates:
        templates = frappe.get_all(
            "ilL-Fixture-Template",
            filters={"is_active": 1},
            fields=["name", "template_code", "template_name"],
            order_by="template_name"
        )
    
    context.templates = templates
    
    # Page title and breadcrumb
    context.title = _("Configure Multi-Segment Fixture")
    context.parents = [{"name": _("Projects"), "route": "/portal/projects"}]
    
    if context.schedule:
        context.parents.append({
            "name": context.schedule.schedule_name,
            "route": f"/portal/schedules/{context.schedule.name}"
        })
    
    return context
