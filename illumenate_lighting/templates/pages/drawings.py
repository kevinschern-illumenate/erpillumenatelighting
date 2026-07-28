# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Drawings Page Controller

Request and track custom drawings and technical documentation.
"""

import frappe
from frappe import _

no_cache = 1


def _get_user_customer(user):
	"""Get the customer linked to the user via Contact."""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
	)
	return _get_user_customer(user)


def get_context(context):
	"""Get context for the drawings portal page."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_is_internal_user,
	)

	is_internal = _is_internal_user(frappe.session.user)
	customer = _get_user_customer(frappe.session.user)

	# Get user's projects for the dropdown (permission-filtered)
	context.projects = frappe.get_list(
		"ilL-Project",
		fields=["name", "project_name"],
		order_by="modified desc",
		limit=50,
	)

	# Build document request filters scoped to the user's customer
	# Internal users see all; portal users see only their own customer's requests
	base_filter = {}
	if not is_internal:
		if customer:
			base_filter["owner_customer"] = customer
		else:
			# No customer link — only show requests they created
			base_filter["owner"] = frappe.session.user

	# Get drawing requests if the doctype exists
	context.pending_requests = []
	context.completed_requests = []
	context.all_requests = []
	context.pending_count = 0

	if frappe.db.exists("DocType", "ilL-Document-Request"):
		# Pending requests (Submitted or In Progress status)
		pending_filter = {**base_filter, "status": ["in", ["Submitted", "In Progress", "Waiting on Customer"]]}
		context.pending_requests = frappe.get_all(
			"ilL-Document-Request",
			filters=pending_filter,
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

		context.pending_count = len(context.pending_requests)

		# Completed requests
		completed_filter = {**base_filter, "status": ["in", ["Completed", "Closed"]]}
		context.completed_requests = frappe.get_all(
			"ilL-Document-Request",
			filters=completed_filter,
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

		# All requests
		context.all_requests = frappe.get_all(
			"ilL-Document-Request",
			filters=base_filter,
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

		# Resolve project names for every list in a single query
		all_rows = context.pending_requests + context.completed_requests + context.all_requests
		project_names = _get_project_names({req.project for req in all_rows if req.project})

		for req in all_rows:
			if req.project:
				req.project_name = project_names.get(req.project)
			req.drawing_type = _request_type_to_drawing_type(req.request_type)
			req.drawing_type_display = req.request_type or _("Request")

		for req in context.pending_requests + context.completed_requests:
			req.custom_reference = req.fixture_or_product_text

		# Resolve attachment presence for completed requests in a single query
		requests_with_files = _get_requests_with_attachments(
			[req.name for req in context.completed_requests]
		)
		for req in context.completed_requests:
			req.has_attachments = req.name in requests_with_files

	# Helper function for icons
	context.drawing_type_icon = _drawing_type_icon

	context.title = _("Drawing Requests")
	context.no_cache = 1

	return context


def _get_project_names(project_names):
	"""Return a {project name: project_name label} map for the given projects."""
	if not project_names:
		return {}

	rows = frappe.get_all(
		"ilL-Project",
		filters={"name": ["in", list(project_names)]},
		fields=["name", "project_name"],
	)
	return {p.name: p.project_name for p in rows}


def _get_requests_with_attachments(request_names):
	"""Return the set of document requests that have at least one attached file."""
	if not request_names:
		return set()

	rows = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "ilL-Document-Request",
			"attached_to_name": ["in", request_names],
		},
		fields=["attached_to_name"],
		distinct=True,
	)
	return {f.attached_to_name for f in rows}


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
