# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Drawings Page Controller

Request and track custom drawings and technical documentation.
"""

import frappe
from frappe import _

no_cache = 1


def get_context(context):
	"""Get context for the drawings portal page."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	# Get user's projects for the dropdown
	context.projects = frappe.get_all(
		"ilL-Project",
		fields=["name", "project_name"],
		order_by="modified desc",
		limit=50,
	)

	# Get drawing requests if the doctype exists
	context.pending_requests = []
	context.completed_requests = []
	context.all_requests = []
	context.pending_count = 0

	if frappe.db.table_exists("ilL-Drawing-Request"):
		# Pending requests
		context.pending_requests = frappe.get_all(
			"ilL-Drawing-Request",
			filters={"status": ["in", ["Pending", "In Progress"]]},
			fields=[
				"name",
				"drawing_type",
				"description",
				"project",
				"custom_reference",
				"priority",
				"status",
				"creation",
			],
			order_by="creation desc",
		)

		# Add project names
		for req in context.pending_requests:
			if req.project:
				req.project_name = frappe.db.get_value("ilL-Project", req.project, "project_name")
			req.drawing_type_display = _get_drawing_type_display(req.drawing_type)

		context.pending_count = len(context.pending_requests)

		# Completed requests
		context.completed_requests = frappe.get_all(
			"ilL-Drawing-Request",
			filters={"status": "Completed"},
			fields=[
				"name",
				"drawing_type",
				"description",
				"project",
				"custom_reference",
				"status",
				"creation",
				"modified",
			],
			order_by="modified desc",
			limit=20,
		)

		for req in context.completed_requests:
			if req.project:
				req.project_name = frappe.db.get_value("ilL-Project", req.project, "project_name")
			req.drawing_type_display = _get_drawing_type_display(req.drawing_type)
			# Check if there are file attachments
			req.has_attachments = frappe.db.count(
				"File",
				{"attached_to_doctype": "ilL-Drawing-Request", "attached_to_name": req.name}
			) > 0

		# All requests
		context.all_requests = frappe.get_all(
			"ilL-Drawing-Request",
			fields=[
				"name",
				"drawing_type",
				"description",
				"project",
				"status",
				"creation",
			],
			order_by="creation desc",
			limit=50,
		)

		for req in context.all_requests:
			if req.project:
				req.project_name = frappe.db.get_value("ilL-Project", req.project, "project_name")
			req.drawing_type_display = _get_drawing_type_display(req.drawing_type)

	# Helper function for icons
	context.drawing_type_icon = _drawing_type_icon

	context.title = _("Drawing Requests")
	context.no_cache = 1

	return context


def _get_drawing_type_display(drawing_type):
	"""Get display name for drawing type."""
	type_map = {
		"shop_drawing": _("Shop Drawing"),
		"spec_sheet": _("Spec Sheet"),
		"installation": _("Installation Guide"),
		"ies_file": _("IES File"),
	}
	return type_map.get(drawing_type, drawing_type)


def _drawing_type_icon(drawing_type):
	"""Get Font Awesome icon for drawing type."""
	icon_map = {
		"shop_drawing": "wrench",
		"spec_sheet": "file-text-o",
		"installation": "puzzle-piece",
		"ies_file": "lightbulb-o",
	}
	return icon_map.get(drawing_type, "file-o")
