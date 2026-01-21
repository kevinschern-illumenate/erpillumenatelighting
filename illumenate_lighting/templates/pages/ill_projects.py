# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe

no_cache = 1

# Page access control - requires login but no specific role
# The get_context function handles permission logic
def get_list_context(context):
	"""Allow website users to access this page."""
	return context


def get_context(context):
	"""Get context for the projects list portal page."""
	# DEBUG: Log everything about the current session
	debug_info = {
		"user": frappe.session.user,
		"user_type": None,
		"roles": [],
		"has_dealer": False,
		"has_customer": False,
		"is_guest": frappe.session.user == "Guest",
		"session_data": str(frappe.session.data) if hasattr(frappe.session, 'data') else "N/A",
	}

	try:
		# Get user details
		if frappe.session.user and frappe.session.user != "Guest":
			user_doc = frappe.get_doc("User", frappe.session.user)
			debug_info["user_type"] = user_doc.user_type
			debug_info["enabled"] = user_doc.enabled
			debug_info["roles"] = frappe.get_roles(frappe.session.user)
			debug_info["has_dealer"] = "Dealer" in debug_info["roles"]
			debug_info["has_customer"] = "Customer" in debug_info["roles"]
	except Exception as e:
		debug_info["user_fetch_error"] = str(e)

	# Log to frappe error log for debugging
	frappe.log_error(
		title="Portal Projects Debug",
		message=frappe.as_json(debug_info, indent=2)
	)

	# Also store debug info in context so we can display it
	context.debug_info = debug_info

	if frappe.session.user == "Guest":
		frappe.log_error(title="Portal Projects - Guest Redirect", message="User is Guest, redirecting to login")
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	# Check if user has any role that grants access to ilL-Project
	user_roles = set(frappe.get_roles(frappe.session.user))
	allowed_roles = {"System Manager", "Administrator", "Dealer", "Customer"}

	frappe.log_error(
		title="Portal Projects - Role Check",
		message=f"User roles: {user_roles}\nAllowed roles: {allowed_roles}\nIntersection: {user_roles & allowed_roles}"
	)

	if not user_roles & allowed_roles:
		frappe.throw(
			f"You don't have permission to access projects. "
			f"Your roles: {list(user_roles)}. Required: one of {list(allowed_roles)}",
			frappe.PermissionError
		)

	# Try to get projects with error handling
	try:
		projects = frappe.get_all(
			"ilL-Project",
			fields=["name", "project_name", "customer", "status", "is_private", "modified"],
			order_by="modified desc",
		)
		frappe.log_error(
			title="Portal Projects - Query Success",
			message=f"Found {len(projects)} projects"
		)
	except Exception as e:
		frappe.log_error(
			title="Portal Projects - Query Error",
			message=f"Error fetching projects: {str(e)}\n\n{frappe.get_traceback()}"
		)
		projects = []

	context.projects = projects
	context.title = "Projects"
	context.no_cache = 1

	return context
