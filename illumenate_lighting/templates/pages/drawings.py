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

	if frappe.db.exists("DocType", "ilL-Document-Request"):
		# Pending requests (Submitted or In Progress status)
		context.pending_requests = frappe.get_all(
			"ilL-Document-Request",
			filters={"status": ["in", ["Submitted", "In Progress", "Waiting on Customer"]]},
			fields=[
				"name",
				"request_type",
				"description",
				"project",
				"fixture_or_product_text",
				"priority",
				"status",
				"creation",
			],
			order_by="creation desc",
		)

		# Add project names and type display
		for req in context.pending_requests:
			if req.project:
				req.project_name = frappe.db.get_value("ilL-Project", req.project, "project_name")
			req.drawing_type = _request_type_to_drawing_type(req.request_type)
			req.drawing_type_display = req.request_type or _("Request")
			req.custom_reference = req.fixture_or_product_text

		context.pending_count = len(context.pending_requests)

		# Completed requests
		context.completed_requests = frappe.get_all(
			"ilL-Document-Request",
			filters={"status": ["in", ["Completed", "Closed"]]},
			fields=[
				"name",
				"request_type",
				"description",
				"project",
				"fixture_or_product_text",
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
			req.drawing_type = _request_type_to_drawing_type(req.request_type)
			req.drawing_type_display = req.request_type or _("Request")
			req.custom_reference = req.fixture_or_product_text
			# Check if there are file attachments
			req.has_attachments = frappe.db.count(
				"File",
				{"attached_to_doctype": "ilL-Document-Request", "attached_to_name": req.name}
			) > 0

		# All requests
		context.all_requests = frappe.get_all(
			"ilL-Document-Request",
			fields=[
				"name",
				"request_type",
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
			req.drawing_type = _request_type_to_drawing_type(req.request_type)
			req.drawing_type_display = req.request_type or _("Request")

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


def _request_type_to_drawing_type(request_type):
	"""Convert request type name to drawing_type key for icon lookup."""
	if not request_type:
		return "other"
	type_map = {
		"Shop Drawing": "shop_drawing",
		"Spec Sheet": "spec_sheet",
		"Installation Guide": "installation",
		"IES File": "ies_file",
	}
	return type_map.get(request_type, "other")


def _drawing_type_icon(drawing_type):
	"""Get Font Awesome icon for drawing type."""
	icon_map = {
		"shop_drawing": "wrench",
		"spec_sheet": "file-text-o",
		"installation": "puzzle-piece",
		"ies_file": "lightbulb-o",
	}
	return icon_map.get(drawing_type, "file-o")
