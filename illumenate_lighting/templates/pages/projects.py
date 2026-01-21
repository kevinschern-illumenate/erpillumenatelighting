# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe

no_cache = 1


def get_context(context):
	"""Get context for the projects list portal page."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	# Check if user has any role that grants access to ilL-Project
	user_roles = set(frappe.get_roles(frappe.session.user))
	allowed_roles = {"System Manager", "Administrator", "Dealer", "Customer"}

	if not user_roles & allowed_roles:
		frappe.throw(
			"You don't have permission to access projects. "
			"Please contact your administrator.",
			frappe.PermissionError
		)

	# Get projects accessible to this user using permission hooks
	projects = frappe.get_all(
		"ilL-Project",
		fields=["name", "project_name", "customer", "status", "is_private", "modified"],
		order_by="modified desc",
	)

	context.projects = projects
	context.title = "Projects"
	context.no_cache = 1

	return context
