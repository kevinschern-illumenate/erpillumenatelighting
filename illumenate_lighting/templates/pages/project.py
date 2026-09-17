# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe

from illumenate_lighting.illumenate_lighting.portal.status import schedule_status_label

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

	# Get schedules for this project, limited to the ones this user may read
	# (a schedule can opt out of inherited project privacy).
	from illumenate_lighting.illumenate_lighting.portal.access import (
		schedule_query_conditions,
	)

	visibility = schedule_query_conditions(frappe.session.user)
	schedules = frappe.db.sql(
		f"""
		SELECT name, schedule_name, status, modified, version, is_locked, version_parent
		FROM `tabilL-Project-Fixture-Schedule`
		WHERE ill_project = %(project)s
		{"AND " + visibility if visibility else ""}
		ORDER BY version_parent ASC, version DESC
		""",
		{"project": project_name},
		as_dict=True,
	)

	# Add line count to each schedule
	for schedule in schedules:
		schedule.lines_count = frappe.db.count(
			"ilL-Child-Fixture-Schedule-Line",
			{"parent": schedule.name},
		)

	# Pre-load contact details for project_manager (still a Contact field)
	contact_details = {}
	if project.get("project_manager"):
		try:
			contact = frappe.get_doc("Contact", project.get("project_manager"))
			contact_details["project_manager"] = {
				"first_name": contact.first_name,
				"last_name": contact.last_name,
				"company_name": contact.company_name
			}
		except Exception:
			contact_details["project_manager"] = None

	# Pre-load customer details for architect, lighting_designer, general_contractor
	customer_role_details = {}
	customer_role_fields = ["architect", "lighting_designer", "general_contractor"]
	for field in customer_role_fields:
		if project.get(field):
			try:
				customer_name_display = frappe.db.get_value("Customer", project.get(field), "customer_name")
				customer_role_details[field] = {
					"customer_name": customer_name_display or project.get(field),
				}
			except Exception:
				customer_role_details[field] = None

	# Get allowed customers for the customer-role dropdowns in the edit modal
	from illumenate_lighting.illumenate_lighting.api.portal import (
		get_allowed_customers_for_project,
	)
	allowed_result = get_allowed_customers_for_project()

	context.project = project
	context.schedules = schedules
	context.can_edit = can_edit
	context.schedule_status_class = schedule_status_class
	context.schedule_status_label = schedule_status_label
	context.title = project.project_name
	context.no_cache = 1
	context.frappe = frappe  # Make frappe available in template
	context.contact_details = contact_details  # Pre-loaded contact details (project_manager)
	context.customer_role_details = customer_role_details  # Pre-loaded customer details
	context.allowed_customers = allowed_result.get("allowed_customers", [])
	context.user_customer = allowed_result.get("user_customer")

	# Get list of territories for new customer creation modal
	context.territories = frappe.get_all("Territory", pluck="name", order_by="name")

	return context


def schedule_status_class(status):
	"""Return CSS class for schedule status badge (shared vocabulary)."""
	from illumenate_lighting.illumenate_lighting.portal.status import (
		schedule_status_class as _status_class,
	)

	return _status_class(status)


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
