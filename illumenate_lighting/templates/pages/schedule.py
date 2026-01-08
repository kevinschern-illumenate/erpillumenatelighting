# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe

no_cache = 1


def get_context(context):
	"""Get context for the schedule detail portal page."""
	if frappe.session.user == "Guest":
		frappe.throw("Please login to view schedules", frappe.PermissionError)

	# Get schedule name from path
	schedule_name = frappe.form_dict.get("schedule")
	if not schedule_name:
		frappe.throw("Schedule not specified", frappe.DoesNotExistError)

	# Get schedule with permission check
	if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
		frappe.throw("Schedule not found", frappe.DoesNotExistError)

	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

	# Check permission via schedule permission hook
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		has_permission,
	)

	if not has_permission(schedule, "read", frappe.session.user):
		frappe.throw("You don't have permission to view this schedule", frappe.PermissionError)

	# Check if user can edit
	can_edit = has_permission(schedule, "write", frappe.session.user)

	# Get project
	project = None
	if schedule.ill_project:
		project = frappe.get_doc("ilL-Project", schedule.ill_project)

	# Get lines
	lines = schedule.lines or []

	# Calculate summary stats
	total_qty = sum(line.qty or 0 for line in lines)
	illumenate_count = sum(1 for line in lines if line.manufacturer_type == "ILLUMENATE")
	other_count = sum(1 for line in lines if line.manufacturer_type == "OTHER")

	context.schedule = schedule
	context.project = project
	context.lines = lines
	context.can_edit = can_edit
	context.total_qty = total_qty
	context.illumenate_count = illumenate_count
	context.other_count = other_count
	context.title = schedule.schedule_name
	context.no_cache = 1

	return context


def schedule_status_class(status):
	"""Return CSS class for schedule status badge."""
	class_map = {
		"DRAFT": "warning",
		"READY": "info",
		"QUOTED": "primary",
		"ORDERED": "success",
		"CLOSED": "secondary",
	}
	return class_map.get(status, "secondary")
