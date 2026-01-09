# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Document Request Portal API

This module provides API endpoints for the document request system on the portal.
Users can request drawings, resources, and other documents, and track their status.
"""

import json
from typing import Union

import frappe
from frappe import _
from frappe.utils import now_datetime


@frappe.whitelist()
def get_request_types() -> dict:
	"""
	Get all active request types for the portal.

	Returns:
		dict: {
			"success": True,
			"request_types": [
				{
					"name": "Shop Drawing",
					"label": "Shop Drawing",
					"icon": "fa-file-pdf-o",
					"description": "...",
					"category": "Drawing"
				}
			]
		}
	"""
	request_types = frappe.get_all(
		"ilL-Request-Type",
		filters={"is_active": 1},
		fields=[
			"name",
			"type_name",
			"portal_label",
			"portal_icon",
			"portal_description",
			"category",
			"show_project_field",
			"show_reference_field",
			"show_fixture_field",
			"show_item_field",
			"show_priority_field",
			"show_due_date_field",
			"default_priority",
		],
		order_by="sort_order asc, type_name asc",
	)

	result = []
	for rt in request_types:
		result.append({
			"name": rt.name,
			"type_name": rt.type_name,
			"label": rt.portal_label or rt.type_name,
			"icon": rt.portal_icon or "fa-file-o",
			"description": rt.portal_description,
			"category": rt.category,
			"show_project_field": rt.show_project_field,
			"show_reference_field": rt.show_reference_field,
			"show_fixture_field": rt.show_fixture_field,
			"show_item_field": rt.show_item_field,
			"show_priority_field": rt.show_priority_field,
			"show_due_date_field": rt.show_due_date_field,
			"default_priority": rt.default_priority,
		})

	return {"success": True, "request_types": result}


@frappe.whitelist()
def get_request_type_fields(request_type: str) -> dict:
	"""
	Get custom fields defined for a request type.

	Args:
		request_type: Name of the request type

	Returns:
		dict: {
			"success": True,
			"fields": [
				{
					"field_key": "mounting_height",
					"label": "Mounting Height",
					"fieldtype": "Data",
					"options": null,
					"mandatory": true,
					"help_text": "...",
					"depends_on": null
				}
			]
		}
	"""
	if not frappe.db.exists("ilL-Request-Type", request_type):
		return {"success": False, "error": "Request type not found"}

	request_type_doc = frappe.get_doc("ilL-Request-Type", request_type)

	fields = []
	for field in request_type_doc.custom_fields or []:
		fields.append({
			"field_key": field.field_key,
			"label": field.label,
			"fieldtype": field.fieldtype,
			"options": field.options,
			"mandatory": field.mandatory,
			"help_text": field.help_text,
			"depends_on": field.depends_on,
			"sort_order": field.sort_order,
		})

	# Sort by sort_order
	fields.sort(key=lambda x: x.get("sort_order", 0))

	return {"success": True, "fields": fields}


@frappe.whitelist()
def create_request(request_data: Union[str, dict]) -> dict:
	"""
	Create a new document request from the portal.

	Args:
		request_data: Dict containing:
			- request_type: Name of the request type
			- project: Optional project name
			- fixture_or_product_text: Optional fixture/product text
			- description: Required description
			- priority: Optional priority (Normal/High/Rush)
			- requested_due_date: Optional due date
			- custom_fields: Dict of field_key -> value for custom fields

	Returns:
		dict: {"success": True/False, "request_name": name, "error": str}
	"""
	if isinstance(request_data, str):
		request_data = json.loads(request_data)

	# Validate required fields
	if not request_data.get("request_type"):
		return {"success": False, "error": "Request type is required"}

	if not request_data.get("description"):
		return {"success": False, "error": "Description is required"}

	if not frappe.db.exists("ilL-Request-Type", request_data.get("request_type")):
		return {"success": False, "error": "Invalid request type"}

	try:
		# Create the request
		doc = frappe.new_doc("ilL-Document-Request")
		doc.request_type = request_data.get("request_type")
		doc.description = request_data.get("description")
		doc.created_from_portal = 1
		doc.status = "Draft"

		# Optional fields
		if request_data.get("project"):
			doc.project = request_data.get("project")

		if request_data.get("fixture_or_product_text"):
			doc.fixture_or_product_text = request_data.get("fixture_or_product_text")

		if request_data.get("item"):
			doc.item = request_data.get("item")

		if request_data.get("priority"):
			doc.priority = request_data.get("priority")

		if request_data.get("requested_due_date"):
			doc.requested_due_date = request_data.get("requested_due_date")

		# Process custom fields
		custom_fields = request_data.get("custom_fields", {})
		if custom_fields:
			request_type_doc = frappe.get_doc("ilL-Request-Type", doc.request_type)
			field_defs = {f.field_key: f for f in request_type_doc.custom_fields or []}

			for field_key, value in custom_fields.items():
				if field_key in field_defs:
					field_def = field_defs[field_key]
					field_value = doc.append("custom_field_values", {})
					field_value.field_key = field_key
					field_value.label = field_def.label

					# Store value in appropriate column based on type
					_store_field_value(field_value, field_def.fieldtype, value)

		doc.insert()

		# Auto-submit if requested
		if request_data.get("auto_submit"):
			doc.status = "Submitted"
			doc.save()

		return {"success": True, "request_name": doc.name}

	except Exception as e:
		frappe.log_error(f"Error creating document request: {str(e)}")
		return {"success": False, "error": str(e)}


def _store_field_value(field_value, fieldtype: str, value):
	"""Store a value in the appropriate column of the field value record."""
	if fieldtype in ["Data", "Select"]:
		field_value.value_text = str(value) if value else ""
		field_value.raw_display = str(value) if value else ""
	elif fieldtype in ["Text", "Small Text", "Long Text"]:
		field_value.value_long_text = str(value) if value else ""
		field_value.raw_display = str(value)[:100] if value else ""
	elif fieldtype == "Int":
		field_value.value_int = int(value) if value else 0
		field_value.raw_display = str(value) if value else ""
	elif fieldtype == "Float":
		field_value.value_float = float(value) if value else 0
		field_value.raw_display = str(value) if value else ""
	elif fieldtype == "Date":
		field_value.value_date = value
		field_value.raw_display = str(value) if value else ""
	elif fieldtype == "Check":
		field_value.value_check = 1 if value else 0
		field_value.raw_display = "Yes" if value else "No"
	elif fieldtype == "Link":
		field_value.value_link_name = str(value) if value else ""
		field_value.raw_display = str(value) if value else ""
	elif fieldtype == "Attach":
		field_value.value_text = str(value) if value else ""
		field_value.raw_display = str(value).split("/")[-1] if value else ""
	else:
		# Fallback to JSON
		field_value.value_json = json.dumps(value)
		field_value.raw_display = str(value)[:100] if value else ""


@frappe.whitelist()
def submit_request(request_name: str) -> dict:
	"""
	Submit a draft request.

	Args:
		request_name: Name of the request to submit

	Returns:
		dict: {"success": True/False, "error": str}
	"""
	if not frappe.db.exists("ilL-Document-Request", request_name):
		return {"success": False, "error": "Request not found"}

	doc = frappe.get_doc("ilL-Document-Request", request_name)

	# Check permission
	from illumenate_lighting.illumenate_lighting.doctype.ill_document_request.ill_document_request import (
		has_permission,
	)
	if not has_permission(doc, "write", frappe.session.user):
		return {"success": False, "error": "Permission denied"}

	if doc.status != "Draft":
		return {"success": False, "error": "Only draft requests can be submitted"}

	try:
		doc.status = "Submitted"
		doc.save()
		return {"success": True}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def list_requests(
	tab: str = "all",
	page: int = 1,
	page_size: int = 20,
	search: str = None,
) -> dict:
	"""
	List document requests for the current user with tab filtering.

	Args:
		tab: "pending", "completed", or "all"
		page: Page number (1-indexed)
		page_size: Number of items per page
		search: Optional search term

	Returns:
		dict: {
			"success": True,
			"requests": [...],
			"total": int,
			"page": int,
			"page_size": int
		}
	"""
	filters = {"hide_from_portal": 0}

	# Apply tab filter
	if tab == "pending":
		filters["portal_status_group"] = "Pending"
	elif tab == "completed":
		filters["portal_status_group"] = "Completed"

	# Build search filter
	or_filters = None
	if search:
		or_filters = [
			["name", "like", f"%{search}%"],
			["request_type", "like", f"%{search}%"],
			["fixture_or_product_text", "like", f"%{search}%"],
		]

	# Get total count first
	total = frappe.db.count(
		"ilL-Document-Request",
		filters=filters,
		or_filters=or_filters,
	)

	# Get paginated results
	start = (page - 1) * page_size
	requests = frappe.get_all(
		"ilL-Document-Request",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"request_type",
			"project",
			"fixture_or_product_text",
			"status",
			"priority",
			"creation",
			"sla_deadline",
			"completed_on",
			"requester_user",
		],
		order_by="creation desc",
		start=start,
		limit=page_size,
	)

	# Enrich with request type labels
	request_type_labels = {}
	for req in requests:
		if req.request_type and req.request_type not in request_type_labels:
			label = frappe.db.get_value(
				"ilL-Request-Type",
				req.request_type,
				"portal_label",
			)
			request_type_labels[req.request_type] = label or req.request_type
		req["request_type_label"] = request_type_labels.get(req.request_type, req.request_type)

		# Get project name if linked
		if req.project:
			project_name = frappe.db.get_value("ilL-Project", req.project, "project_name")
			req["project_name"] = project_name

	return {
		"success": True,
		"requests": requests,
		"total": total,
		"page": page,
		"page_size": page_size,
	}


@frappe.whitelist()
def get_request_detail(request_name: str) -> dict:
	"""
	Get detailed information about a specific request.

	Args:
		request_name: Name of the request

	Returns:
		dict: Full request details including custom fields and deliverables
	"""
	if not frappe.db.exists("ilL-Document-Request", request_name):
		return {"success": False, "error": "Request not found"}

	doc = frappe.get_doc("ilL-Document-Request", request_name)

	# Check permission
	from illumenate_lighting.illumenate_lighting.doctype.ill_document_request.ill_document_request import (
		has_permission,
	)
	if not has_permission(doc, "read", frappe.session.user):
		return {"success": False, "error": "Permission denied"}

	# Get request type info
	request_type_info = None
	if doc.request_type:
		rt = frappe.get_doc("ilL-Request-Type", doc.request_type)
		request_type_info = {
			"name": rt.name,
			"label": rt.portal_label or rt.type_name,
			"icon": rt.portal_icon,
		}

	# Get project info
	project_info = None
	if doc.project:
		project = frappe.get_doc("ilL-Project", doc.project)
		project_info = {
			"name": project.name,
			"project_name": project.project_name,
		}

	# Build custom field values
	custom_fields = []
	for fv in doc.custom_field_values or []:
		custom_fields.append({
			"field_key": fv.field_key,
			"label": fv.label,
			"value": fv.raw_display or fv.get_value(),
		})

	# Build deliverables (only published ones for portal users)
	deliverables = []
	is_internal = "System Manager" in frappe.get_roles(frappe.session.user)

	for idx, d in enumerate(doc.deliverables or []):
		if is_internal or d.is_published_to_portal:
			deliverables.append({
				"idx": idx,
				"deliverable_type": d.deliverable_type,
				"file": d.file,
				"filename": d.file.split("/")[-1] if d.file else None,
				"notes": d.notes,
				"version": d.version,
				"is_published": d.is_published_to_portal,
				"published_on": d.published_on,
			})

	# Get attachments
	attachments = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "ilL-Document-Request",
			"attached_to_name": doc.name,
			"is_private": 0,
		},
		fields=["name", "file_name", "file_url", "creation"],
	)

	return {
		"success": True,
		"request": {
			"name": doc.name,
			"request_type": doc.request_type,
			"request_type_info": request_type_info,
			"status": doc.status,
			"portal_status_group": doc.portal_status_group,
			"priority": doc.priority,
			"project": doc.project,
			"project_info": project_info,
			"fixture_or_product_text": doc.fixture_or_product_text,
			"item": doc.item,
			"description": doc.description,
			"requested_due_date": doc.requested_due_date,
			"creation": doc.creation,
			"sla_deadline": doc.sla_deadline,
			"completed_on": doc.completed_on,
			"requester_user": doc.requester_user,
			"custom_fields": custom_fields,
			"deliverables": deliverables,
			"attachments": attachments,
			"can_edit": doc.status == "Draft" and doc.requester_user == frappe.session.user,
			"can_add_attachment": doc.status in ["Draft", "Submitted", "In Progress", "Waiting on Customer"],
		},
	}


@frappe.whitelist()
def add_request_attachment(request_name: str, file_url: str, filename: str = None) -> dict:
	"""
	Add an attachment to a request.

	Args:
		request_name: Name of the request
		file_url: URL of the uploaded file
		filename: Optional filename

	Returns:
		dict: {"success": True/False, "error": str}
	"""
	if not frappe.db.exists("ilL-Document-Request", request_name):
		return {"success": False, "error": "Request not found"}

	doc = frappe.get_doc("ilL-Document-Request", request_name)

	# Check permission
	from illumenate_lighting.illumenate_lighting.doctype.ill_document_request.ill_document_request import (
		has_permission,
	)
	if not has_permission(doc, "write", frappe.session.user):
		return {"success": False, "error": "Permission denied"}

	# Check status allows attachments
	if doc.status in ["Completed", "Closed", "Cancelled"]:
		return {"success": False, "error": "Cannot add attachments to this request"}

	try:
		# Create file record
		file_doc = frappe.new_doc("File")
		file_doc.file_url = file_url
		file_doc.file_name = filename or file_url.split("/")[-1]
		file_doc.attached_to_doctype = "ilL-Document-Request"
		file_doc.attached_to_name = request_name
		file_doc.is_private = 0
		file_doc.insert(ignore_permissions=True)

		return {"success": True, "file_name": file_doc.name}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def add_deliverable(
	request_name: str,
	file_url: str,
	deliverable_type: str = None,
	notes: str = None,
	version: str = None,
	publish: int = 0,
) -> dict:
	"""
	Add a deliverable to a request (internal use only).

	Args:
		request_name: Name of the request
		file_url: URL of the uploaded file
		deliverable_type: Type of deliverable
		notes: Optional notes
		version: Optional version string
		publish: 1 to publish immediately

	Returns:
		dict: {"success": True/False, "error": str}
	"""
	# Check internal permission
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		return {"success": False, "error": "Only internal users can add deliverables"}

	if not frappe.db.exists("ilL-Document-Request", request_name):
		return {"success": False, "error": "Request not found"}

	doc = frappe.get_doc("ilL-Document-Request", request_name)

	try:
		deliverable = doc.append("deliverables", {})
		deliverable.file = file_url
		deliverable.deliverable_type = deliverable_type
		deliverable.notes = notes
		deliverable.version = version

		if publish:
			deliverable.is_published_to_portal = 1
			deliverable.published_on = now_datetime()
			deliverable.published_by = frappe.session.user

		doc.save()

		return {"success": True, "idx": len(doc.deliverables) - 1}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def publish_deliverable(request_name: str, deliverable_idx: int) -> dict:
	"""
	Publish a deliverable to make it visible on the portal.

	Args:
		request_name: Name of the request
		deliverable_idx: Index of the deliverable

	Returns:
		dict: {"success": True/False, "error": str}
	"""
	# Check internal permission
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		return {"success": False, "error": "Only internal users can publish deliverables"}

	if not frappe.db.exists("ilL-Document-Request", request_name):
		return {"success": False, "error": "Request not found"}

	doc = frappe.get_doc("ilL-Document-Request", request_name)

	try:
		doc.publish_deliverable(int(deliverable_idx))
		return {"success": True}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def update_request_status(request_name: str, new_status: str) -> dict:
	"""
	Update the status of a request (internal use only).

	Args:
		request_name: Name of the request
		new_status: New status value

	Returns:
		dict: {"success": True/False, "error": str}
	"""
	# Check internal permission
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		return {"success": False, "error": "Only internal users can update status"}

	if not frappe.db.exists("ilL-Document-Request", request_name):
		return {"success": False, "error": "Request not found"}

	valid_statuses = ["Draft", "Submitted", "In Progress", "Waiting on Customer", "Completed", "Closed", "Cancelled"]
	if new_status not in valid_statuses:
		return {"success": False, "error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}

	try:
		doc = frappe.get_doc("ilL-Document-Request", request_name)
		doc.status = new_status
		doc.save()
		return {"success": True}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_request_counts() -> dict:
	"""
	Get counts of requests by status group for the current user.

	Returns:
		dict: {"pending": int, "completed": int, "all": int}
	"""
	pending = frappe.db.count(
		"ilL-Document-Request",
		filters={"portal_status_group": "Pending", "hide_from_portal": 0},
	)

	completed = frappe.db.count(
		"ilL-Document-Request",
		filters={"portal_status_group": "Completed", "hide_from_portal": 0},
	)

	return {
		"success": True,
		"pending": pending,
		"completed": completed,
		"all": pending + completed,
	}
