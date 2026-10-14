# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe

from illumenate_lighting.illumenate_lighting.portal.web_guard import require_login

no_cache = 1


def get_context(context):
	"""Get context for the projects list portal page."""
	require_login()

	# Get projects accessible to this user (frappe.get_list applies
	# get_permission_query_conditions, unlike frappe.get_all which ignores permissions)
	projects = frappe.get_list(
		"ilL-Project",
		fields=["name", "project_name", "customer", "status", "is_private", "modified"],
		order_by="modified desc",
	)

	context.projects = projects
	context.title = "Projects"
	context.no_cache = 1

	return context
