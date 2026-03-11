# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe

no_cache = 1


def get_context(context):
    """Get context for the LED Tape / LED Neon configurator portal page."""
    if frappe.session.user == "Guest":
        frappe.throw("Please login to configure products", frappe.PermissionError)

    # Product category from URL: /configure-tape?category=LED%20Tape (or LED Neon)
    product_category = frappe.form_dict.get("category", "LED Tape")
    if product_category not in ("LED Tape", "LED Neon"):
        product_category = "LED Tape"

    # Optional schedule context (pre-fill from fixture schedule line UI)
    schedule_name = frappe.form_dict.get("schedule")
    line_idx = frappe.form_dict.get("line_idx")

    schedule = None
    can_save = False
    project_name = None

    if schedule_name:
        if frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
            schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

            from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
                has_permission,
            )
            if has_permission(schedule, "write", frappe.session.user):
                can_save = True

            project_name = schedule.ill_project

    # Available tape specs for this product category
    tape_specs = frappe.get_all(
        "ilL-Spec-LED Tape",
        filters={"product_category": product_category},
        fields=["name", "item", "led_package", "watts_per_foot",
                "cut_increment_mm", "is_free_cutting", "pcb_mounting",
                "pcb_finish", "leader_cable_item"],
        order_by="name asc",
    )

    is_system_manager = "System Manager" in frappe.get_roles(frappe.session.user)

    context.product_category = product_category
    context.is_neon = product_category == "LED Neon"
    context.schedule = schedule
    context.schedule_name = schedule_name or ""
    context.project_name = project_name or ""
    context.line_idx = int(line_idx) if line_idx is not None else None
    context.can_save = can_save
    context.is_system_manager = is_system_manager
    context.tape_specs = tape_specs
    context.title = f"Configure {product_category}"
    context.no_cache = 1

    return context
