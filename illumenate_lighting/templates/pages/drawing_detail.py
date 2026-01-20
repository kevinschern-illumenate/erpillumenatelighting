# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Drawing Detail Page Controller

Detailed view of a single document request.
"""

import frappe
from frappe import _

no_cache = 1


def get_context(context):
	"""Get context for the drawing detail portal page."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	request_name = frappe.form_dict.get("request")

	if not request_name:
		context.request = None
		context.title = _("Request Not Found")
		return context

	# Get request details via API (handles existence check and permissions)
	from illumenate_lighting.illumenate_lighting.api.document_requests import get_request_detail

	result = get_request_detail(request_name)

	if not result.get("success"):
		context.request = None
		context.title = _("Request Not Found")
		return context

	context.request = frappe._dict(result.get("request", {}))

	# Get request type info for icons and display
	context.request_type_info = context.request.get("request_type_info") or {}

	# Get project info if present
	context.project_info = context.request.get("project_info")

	# Get custom fields
	context.custom_fields = context.request.get("custom_fields", [])

	# Get deliverables
	context.deliverables = context.request.get("deliverables", [])

	# Get attachments
	context.attachments = context.request.get("attachments", [])

	# Calculate status display info
	context.status_class = _get_status_class(context.request.status)

	# Permission flags
	context.can_edit = context.request.get("can_edit", False)
	context.can_add_attachment = context.request.get("can_add_attachment", False)

	# Icon helper
	context.drawing_type_icon = _drawing_type_icon

	context.title = context.request.name
	context.no_cache = 1

	return context


def _get_status_class(status):
	"""Get CSS class for status badge."""
	status_map = {
		"Draft": "secondary",
		"Submitted": "warning",
		"In Progress": "info",
		"Waiting on Customer": "warning",
		"Completed": "success",
		"Closed": "secondary",
		"Cancelled": "danger",
	}
	return status_map.get(status, "secondary")


def _drawing_type_icon(request_type):
	"""Get Font Awesome icon for request type."""
	if not request_type:
		return "file-o"

	type_lower = request_type.lower()
	if "shop" in type_lower or "drawing" in type_lower:
		return "wrench"
	elif "spec" in type_lower:
		return "file-text-o"
	elif "install" in type_lower:
		return "puzzle-piece"
	elif "ies" in type_lower or "light" in type_lower:
		return "lightbulb-o"
	return "file-o"
