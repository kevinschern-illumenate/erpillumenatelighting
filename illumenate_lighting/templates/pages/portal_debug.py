# Copyright (c) 2026, ilLumenate Lighting and contributors
# Debug page to test portal access

import frappe

no_cache = 1


def get_context(context):
	"""Debug context for testing portal access."""
	frappe.log_error(
		title="Portal Debug Page Accessed",
		message=f"User: {frappe.session.user}"
	)
	
	context.user_roles = frappe.get_roles(frappe.session.user) if frappe.session.user != "Guest" else []
	
	if frappe.session.user and frappe.session.user != "Guest":
		try:
			user_doc = frappe.get_doc("User", frappe.session.user)
			context.user_type = user_doc.user_type
		except Exception:
			context.user_type = "Error fetching"
	else:
		context.user_type = "N/A (Guest)"
	
	return context
