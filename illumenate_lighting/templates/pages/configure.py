# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe

no_cache = 1


def get_context(context):
	"""Get context for the configurator portal page."""
	if frappe.session.user == "Guest":
		frappe.throw("Please login to configure fixtures", frappe.PermissionError)

	# Get optional schedule context
	schedule_name = frappe.form_dict.get("schedule")
	line_idx = frappe.form_dict.get("line_idx")
	template_code = frappe.form_dict.get("template")

	schedule = None
	can_save = False

	if schedule_name:
		if frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
			schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

			# Check permission
			from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
				has_permission,
			)

			if has_permission(schedule, "write", frappe.session.user):
				can_save = True

	# Get available templates
	templates = frappe.get_all(
		"ilL-Fixture-Template",
		filters={"is_active": 1},
		fields=["template_code", "template_name"],
		order_by="template_name asc",
	)

	# Determine if pricing should be shown based on user role
	# For MVP, show pricing to all users (can be restricted later)
	show_pricing = True

	# Check if specific roles should hide pricing
	user_roles = frappe.get_roles(frappe.session.user)
	# Example: hide pricing for certain roles
	# if "ilL Portal Customer" in user_roles and "ilL Dealer" not in user_roles:
	#     show_pricing = False

	context.schedule = schedule
	context.line_idx = int(line_idx) if line_idx is not None else None
	context.can_save = can_save
	context.templates = templates
	context.selected_template = template_code
	context.show_pricing = show_pricing
	context.title = "Configure Fixture"
	context.no_cache = 1

	return context
