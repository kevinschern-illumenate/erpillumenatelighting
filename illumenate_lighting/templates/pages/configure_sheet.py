# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.throw("Please login to configure products", frappe.PermissionError)
    schedule_name = frappe.form_dict.get("schedule")
    line_idx = frappe.form_dict.get("line_idx")
    schedule = None
    can_save = False
    project_name = None
    if schedule_name and frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
        schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)
        from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import has_permission
        can_save = bool(has_permission(schedule, "write", frappe.session.user))
        project_name = schedule.ill_project
    from illumenate_lighting.illumenate_lighting.api.portal import get_led_sheet_templates, get_configured_sheet_for_line
    templates = get_led_sheet_templates().get("templates", [])
    existing = None
    if schedule_name and line_idx:
        existing = get_configured_sheet_for_line(schedule_name, int(line_idx)).get("data")
    context.title = "Configure LED Sheet"
    context.schedule = schedule
    context.schedule_name = schedule_name or ""
    context.project_name = project_name or ""
    context.line_idx = int(line_idx) if line_idx is not None else None
    context.can_save = can_save
    context.led_sheet_templates = templates
    context.existing_configured_sheet = existing
    context.no_cache = 1
    return context
