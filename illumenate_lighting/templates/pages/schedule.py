# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe

no_cache = 1


def get_context(context):
	"""Get context for the schedule detail portal page."""
	if frappe.session.user == "Guest":
		frappe.throw("Please login to view schedules", frappe.PermissionError)

	# Check if this is a new schedule creation (routed from /portal/projects/<project>/schedules/new)
	project_name = frappe.form_dict.get("project")
	if project_name:
		# This is the new schedule creation flow
		return _get_new_schedule_context(context, project_name)

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

	# Create JSON-serializable line data for JavaScript
	lines_json = []
	for line in lines:
		lines_json.append({
			"line_id": line.line_id,
			"qty": line.qty,
			"location": line.location,
			"manufacturer_type": line.manufacturer_type,
			"manufacturer_name": line.manufacturer_name,
			"model_number": line.model_number,
			"notes": line.notes,
			"configured_fixture": line.configured_fixture,
			"ill_item_code": line.ill_item_code,
			"manufacturable_length_mm": line.manufacturable_length_mm,
		})

	context.schedule = schedule
	context.project = project
	context.lines = lines
	context.lines_json = lines_json
	context.can_edit = can_edit
	context.total_qty = total_qty
	context.illumenate_count = illumenate_count
	context.other_count = other_count
	context.schedule_status_class = schedule_status_class
	context.title = schedule.schedule_name
	context.no_cache = 1

	return context


def _get_new_schedule_context(context, project_name):
	"""Get context for creating a new schedule."""
	# Validate project exists
	if not frappe.db.exists("ilL-Project", project_name):
		frappe.throw("Project not found", frappe.DoesNotExistError)

	project = frappe.get_doc("ilL-Project", project_name)

	# Check permission on project (user must be able to write to project to create schedules)
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		has_permission as project_has_permission,
	)

	if not project_has_permission(project, "write", frappe.session.user):
		frappe.throw("You don't have permission to create schedules in this project", frappe.PermissionError)

	context.is_new = True
	context.project = project
	context.title = "Create Schedule"
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
