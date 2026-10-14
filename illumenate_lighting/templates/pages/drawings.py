# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Drawings Page Controller

Request and track custom drawings and technical documentation.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.web_guard import require_login

no_cache = 1


def _get_user_customer(user):
	"""Get the customer linked to the user via Contact."""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
	)
	return _get_user_customer(user)


def get_context(context):
	"""Get context for the drawings portal page."""
	require_login()

	# Request types configured on Desk drive the form (DESK-7).
	from illumenate_lighting.illumenate_lighting.api.document_requests import portal_request_types

	context.request_types = portal_request_types()

	# Recent readable projects; the picker searches the rest (project_list.search).
	context.projects = frappe.get_list(
		"ilL-Project",
		filters={"status": ["!=", "ARCHIVED"]},
		fields=["name", "project_name"],
		order_by="modified desc",
		limit=20,
	)

	# REL-8: every list uses the same scope as the dashboard counts (the doctype's
	# permission predicate), so lists and counts agree and collaborators see their projects.
	from illumenate_lighting.illumenate_lighting.api.document_requests import _scoped_request_count
	from illumenate_lighting.illumenate_lighting.portal.drawing_list import page_number, requests

	context.pending_requests = []
	context.completed_requests = []
	context.all_requests = []
	context.pending_count = 0
	context.page = page_number(frappe.form_dict.get("page"))
	context.has_more = False

	if frappe.db.exists("DocType", "ilL-Document-Request"):
		context.pending_requests, _more = requests("pending", page_size=50)
		context.pending_count = _scoped_request_count("pending")
		context.completed_requests, _more = requests("completed")
		context.all_requests, context.has_more = requests("all", page=context.page)

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
