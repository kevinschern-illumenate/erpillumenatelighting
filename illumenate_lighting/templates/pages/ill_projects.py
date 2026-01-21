# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe

no_cache = 1


def get_context(context):
	"""Get context for the projects list portal page."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

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
