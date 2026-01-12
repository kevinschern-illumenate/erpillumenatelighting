# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe

no_cache = 1


def get_context(context):
	"""Get context for the project detail portal page."""
	if frappe.session.user == "Guest":
		frappe.throw("Please login to view projects", frappe.PermissionError)

	# Get project name from path
	project_name = frappe.form_dict.get("project")

	# Handle new project creation
	if project_name == "new":
		return _get_new_project_context(context)

	if not project_name:
		frappe.throw("Project not specified", frappe.DoesNotExistError)

	# Get project with permission check
	if not frappe.db.exists("ilL-Project", project_name):
		frappe.throw("Project not found", frappe.DoesNotExistError)

	project = frappe.get_doc("ilL-Project", project_name)

	# Check permission
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		has_permission,
	)

	if not has_permission(project, "read", frappe.session.user):
		frappe.throw("You don't have permission to view this project", frappe.PermissionError)

	# Check if user can edit
	can_edit = has_permission(project, "write", frappe.session.user)

	# Get schedules for this project
	schedules = frappe.get_all(
		"ilL-Project-Fixture-Schedule",
		filters={"ill_project": project_name},
		fields=["name", "schedule_name", "status", "modified"],
		order_by="modified desc",
	)

	# Add line count to each schedule
	for schedule in schedules:
		schedule.lines_count = frappe.db.count(
			"ilL-Child-Fixture-Schedule-Line",
			{"parent": schedule.name},
		)

	context.project = project
	context.schedules = schedules
	context.can_edit = can_edit
	context.schedule_status_class = schedule_status_class
	context.title = project.project_name
	context.no_cache = 1
	context.frappe = frappe  # Make frappe available in template

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


def _get_new_project_context(context):
	"""Get context for creating a new project."""
	from illumenate_lighting.illumenate_lighting.api.portal import (
		get_allowed_customers_for_project,
	)

	# Get allowed customers for the dropdown
	allowed_result = get_allowed_customers_for_project()

	context.is_new = True
	context.user_customer = allowed_result.get("user_customer")
	context.allowed_customers = allowed_result.get("allowed_customers", [])
	context.title = "Create Project"
	context.no_cache = 1

	# Get list of territories for new customer creation
	context.territories = frappe.get_all("Territory", pluck="name", order_by="name")

	return context
