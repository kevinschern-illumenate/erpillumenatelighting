# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe

no_cache = 1


def get_context(context):
	"""Get context for the project collaborators portal page."""
	if frappe.session.user == "Guest":
		frappe.throw("Please login to manage collaborators", frappe.PermissionError)

	# Get project name from path
	project_name = frappe.form_dict.get("project")

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

	# Check if user can manage collaborators (only owner or System Manager)
	is_owner = project.owner == frappe.session.user
	is_system_manager = "System Manager" in frappe.get_roles(frappe.session.user)
	can_manage = is_owner or is_system_manager

	# Get current collaborators with user details
	collaborators = []
	for collab in project.collaborators or []:
		user_doc = frappe.get_doc("User", collab.user) if frappe.db.exists("User", collab.user) else None
		collaborators.append({
			"user": collab.user,
			"full_name": user_doc.full_name if user_doc else collab.user,
			"email": user_doc.email if user_doc else collab.user,
			"access_level": collab.access_level,
			"is_active": collab.is_active,
			"added_on": collab.added_on,
		})

	# Get available users for adding as collaborators
	available_users = _get_available_users(project)

	context.project = project
	context.collaborators = collaborators
	context.available_users = available_users
	context.can_manage = can_manage
	context.is_owner = is_owner
	context.title = f"Collaborators - {project.project_name}"
	context.no_cache = 1

	return context


def _get_available_users(project):
	"""
	Get users available to be added as collaborators.

	Returns users who:
	1. Are enabled
	2. Are not already collaborators
	3. Are linked to the same customer as the current user (or any user if System Manager)
	"""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
		_is_internal_user,
	)
	from illumenate_lighting.illumenate_lighting.api.portal import (
		_get_users_for_customer,
	)

	# Get existing collaborator emails
	existing_users = {c.user for c in project.collaborators or []}
	existing_users.add(project.owner)  # Owner is implicit collaborator

	is_internal = _is_internal_user(frappe.session.user)

	if is_internal:
		# System Managers / internal users see all users
		all_users = frappe.get_all(
			"User",
			filters={
				"enabled": 1,
				"name": ["not in", ["Guest", "Administrator"]],
			},
			fields=["name", "full_name", "email"],
		)
	else:
		# Non-internal users: filter by company
		user_customer = _get_user_customer(frappe.session.user)
		if not user_customer:
			return []

		company_user_emails = _get_users_for_customer(user_customer)
		if not company_user_emails:
			return []

		all_users = frappe.get_all(
			"User",
			filters={
				"enabled": 1,
				"name": ["in", list(company_user_emails)],
			},
			fields=["name", "full_name", "email"],
		)

	# Filter to users not already collaborators
	available = []
	for user in all_users:
		if user.name not in existing_users:
			available.append({
				"value": user.name,
				"label": f"{user.full_name} ({user.email})" if user.full_name else user.email,
				"full_name": user.full_name or user.email,
				"email": user.email,
			})

	# Sort by label
	available.sort(key=lambda x: x["label"])

	# Remove duplicates (in case user appears in both lists)
	seen = set()
	unique_available = []
	for u in available:
		if u["value"] not in seen:
			seen.add(u["value"])
			unique_available.append(u)

	return unique_available
