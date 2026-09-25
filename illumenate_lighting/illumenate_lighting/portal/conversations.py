"""Append-only customer replies and staff notes with parent-scoped access."""

import json

import frappe

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint

MESSAGE = "ilL-Portal-Message"
COMMERCIAL = ("ilL-Quote-Request", "ilL-Order-Intake", "ilL-Order-Change")
PARENTS = ("ilL-Document-Request", "Issue", *COMMERCIAL)
CLOSED = ("Completed", "Closed", "Cancelled", "Resolved")


def is_staff(doc, user=None):
	user = user or frappe.session.user
	if doc.doctype in COMMERCIAL:
		from illumenate_lighting.illumenate_lighting.portal.staff import allowed

		if not allowed("sales", user):
			return False
		if doc.doctype == "ilL-Quote-Request":
			return bool(frappe.has_permission("Quotation", "write", user=user))
		order = frappe.get_doc("Sales Order", doc.sales_order)
		return bool(frappe.has_permission("Sales Order", "write", doc=order, user=user))
	if doc.doctype == "ilL-Document-Request":
		from illumenate_lighting.illumenate_lighting.doctype.ill_document_request.ill_document_request import (
			_is_request_staff,
		)

		return _is_request_staff(doc, user)
	return bool(
		user != "Guest"
		and frappe.db.get_value("User", user, "enabled")
		and frappe.db.get_value("User", user, "user_type") == "System User"
		and frappe.has_permission("Issue", "write", doc=doc, user=user)
	)


def parent(parent_type, parent_name, user=None, *, lock=False):
	from illumenate_lighting.illumenate_lighting.portal.files import _context_access

	if parent_type not in PARENTS or not _context_access(parent_type, parent_name, "read", user):
		frappe.throw("Conversation unavailable", frappe.PermissionError)
	if lock:
		frappe.db.sql(f"select name from `tab{parent_type}` where name=%s for update", parent_name)
		if not _context_access(parent_type, parent_name, "read", user):
			frappe.throw("Conversation unavailable", frappe.PermissionError)
	return frappe.get_doc(parent_type, parent_name)


def has_permission(doc, ptype="read", user=None):
	user = user or frappe.session.user
	if ptype not in ("read", "select"):
		return False
	try:
		context = parent(doc.reference_type, doc.reference_name, user)
	except (frappe.PermissionError, frappe.DoesNotExistError):
		return False
	return doc.visibility == "Customer" or is_staff(context, user)


def get_permission_query_conditions(user=None):
	# The API does the parent join and projects only readable messages. There is
	# no unscoped native list, including for staff with unrelated assignments.
	return "1=0"


def _pagination(page, page_size):
	try:
		page, page_size = int(page), int(page_size)
	except (TypeError, ValueError):
		frappe.throw("Invalid page")
	if page < 1 or not 1 <= page_size <= 50:
		frappe.throw("Invalid page")
	return page, page_size


@frappe.whitelist()
def list_messages(parent_type, parent_name, page=1, page_size=20):
	from illumenate_lighting.illumenate_lighting.portal.files import list_files

	doc = parent(parent_type, parent_name)
	page, page_size = _pagination(page, page_size)
	staff = is_staff(doc)
	filters = {"reference_type": parent_type, "reference_name": parent_name}
	if not staff:
		filters["visibility"] = "Customer"
	rows = frappe.get_all(
		MESSAGE,
		filters=filters,
		fields=["name", "actor", "creation", "body", "visibility", "action"],
		order_by="creation desc, name desc",
		limit_start=(page - 1) * page_size,
		limit_page_length=page_size,
	)
	for row in rows:
		row["files"] = list_files(MESSAGE, row.name)
	return {
		"messages": rows,
		"total": frappe.db.count(MESSAGE, filters),
		"page": page,
		"page_size": page_size,
		"status": doc.get("state") if doc.doctype in COMMERCIAL else doc.status,
		"is_staff": staff,
		"can_reply": _open(doc),
		"next_action_by": doc.get("ill_next_action_by") or "Staff",
	}


def _open(doc):
	if doc.doctype in COMMERCIAL:
		return doc.state not in ("APPROVED", "REJECTED", "WITHDRAWN", "ISSUED", "CLOSED", "COMPLETED")
	return doc.status not in CLOSED


def _transition(doc, staff, action, visibility):
	if visibility == "Internal":
		if action != "REPLY":
			frappe.throw("Internal notes cannot change customer status")
		return
	if doc.doctype in COMMERCIAL:
		if not _open(doc):
			frappe.throw("This request is closed. Start a new request for further changes.")
		if action not in ("REPLY", "REQUEST_INFO"):
			frappe.throw("Use the commercial review actions to decide this request")
		if action == "REQUEST_INFO":
			doc.state, doc.ill_next_action_by = "INFORMATION_NEEDED", "Customer"
		elif not staff:
			doc.state, doc.ill_next_action_by = "UNDER_REVIEW", "Staff"
		doc.save(ignore_permissions=True)
		return
	if action == "REPLY":
		if doc.status in CLOSED:
			frappe.throw("This conversation is closed. Staff must reopen it before replying.")
		if not staff:
			doc.ill_next_action_by = "Staff"
			if doc.status == "Waiting on Customer":
				doc.status = "In Progress"
	elif action == "REQUEST_INFO":
		if doc.status in CLOSED:
			frappe.throw("Reopen this conversation before requesting information")
		doc.ill_next_action_by = "Customer"
		if doc.doctype == "ilL-Document-Request":
			doc.status = "Waiting on Customer"
	elif action == "RESOLVE":
		doc.ill_next_action_by = "None"
		doc.status = "Completed" if doc.doctype == "ilL-Document-Request" else "Resolved"
	elif action == "REOPEN":
		if doc.status not in CLOSED:
			frappe.throw("This conversation is already open")
		doc.ill_next_action_by = "Staff"
		doc.status = "In Progress" if doc.doctype == "ilL-Document-Request" else "Open"
	else:
		frappe.throw("Choose a supported conversation action")
	doc.flags.portal_thread_transition = True
	doc.save(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
@atomic_build
def reply(
	parent_type, parent_name, body, idempotency_key, visibility="Customer", action="REPLY", file_ids=None
):
	from illumenate_lighting.illumenate_lighting.portal.files import finalize_files

	doc = parent(parent_type, parent_name, lock=True)
	staff = is_staff(doc)
	if visibility not in ("Customer", "Internal") or (
		not staff and (visibility != "Customer" or action != "REPLY")
	):
		frappe.throw("This action requires assigned staff", frappe.PermissionError)
	if not isinstance(body, str) or not body.strip() or len(body) > 20000:
		frappe.throw("Enter a message of 1 to 20,000 characters")
	if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 128:
		frappe.throw("A reply retry key is required")
	if isinstance(file_ids, str):
		file_ids = json.loads(file_ids)
	file_ids = file_ids or []
	if (
		not isinstance(file_ids, list)
		or len(file_ids) > 10
		or any(not isinstance(key, str) for key in file_ids)
	):
		frappe.throw("Choose at most 10 uploaded files")
	request_hash = fingerprint(
		{"body": body.strip(), "visibility": visibility, "action": action, "files": file_ids}
	)
	key = fingerprint(
		{"actor": frappe.session.user, "parent": [parent_type, parent_name], "key": idempotency_key}
	)
	existing = frappe.db.get_value(MESSAGE, {"request_key": key}, ["name", "request_hash"], as_dict=True)
	if existing:
		if existing.request_hash != request_hash:
			frappe.throw("This reply key has already been used for different content")
		return {"success": True, "message_name": existing.name, "already_existed": True}
	_transition(doc, staff, action, visibility)
	message = frappe.get_doc(
		{
			"doctype": MESSAGE,
			"reference_type": parent_type,
			"reference_name": parent_name,
			"actor": frappe.session.user,
			"body": body.strip(),
			"visibility": visibility,
			"action": action,
			"request_key": key,
			"request_hash": request_hash,
		}
	)
	message.flags.conversation_service_write = True
	message.insert(ignore_permissions=True)
	finalize_files(file_ids, MESSAGE, message.name, allow_unbound=True)
	_notify(doc, message, staff)
	return {"success": True, "message_name": message.name}


def _notify(doc, message, staff):
	if message.visibility != "Customer":
		return
	from illumenate_lighting.illumenate_lighting.portal.notifications import notify_user

	if staff:
		recipients = [doc.get("requester_user") or doc.get("raised_by") or doc.get("requested_by")]
	else:
		recipients = [doc.get("assigned_to") or doc.get("ill_support_owner")]
	path = "drawings" if doc.doctype == "ilL-Document-Request" else "support"
	link_name = doc.name
	if doc.doctype == "ilL-Quote-Request":
		path, link_name = "quote-requests", doc.name
	elif doc.doctype in ("ilL-Order-Intake", "ilL-Order-Change"):
		path, link_name = "orders", doc.sales_order
	for recipient in recipients:
		if recipient and recipient != frappe.session.user:
			notify_user(
				recipient,
				"notify_drawings" if path == "drawings" else "notify_orders",
				"A reply is available in your portal conversation",
				f'<p><a href="{frappe.utils.get_url()}/portal/{path}/{frappe.utils.escape_html(link_name)}">Open the conversation</a> to read the reply.</p>',
				reference_doctype=MESSAGE,
				reference_name=message.name,
			)
