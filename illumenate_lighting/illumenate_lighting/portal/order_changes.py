"""Customer requests around an order, without rewriting issued acknowledgment evidence."""

import json

import frappe

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json, fingerprint
from illumenate_lighting.illumenate_lighting.portal.order_intake import _buyer
from illumenate_lighting.illumenate_lighting.portal.order_review import _staff, snapshot
from illumenate_lighting.illumenate_lighting.portal.orders import load_accessible_sales_order

DOCTYPE = "ilL-Order-Change"
TYPES = ("Change", "Cancellation", "Reorder", "Replacement")


def can_access(doc, ptype="read", user=None):
	order = load_accessible_sales_order(doc.sales_order, user)
	return bool(order) and (
		ptype in ("read", "select", "print", "report")
		or (ptype == "write" and doc.state in ("SUBMITTED", "UNDER_REVIEW", "INFORMATION_NEEDED"))
	)


def has_permission(doc, ptype="read", user=None):
	# Writes pass through revision-checked commands, never native REST editing.
	return ptype in ("read", "select", "report", "print") and can_access(doc, ptype, user)


def get_permission_query_conditions(user=None):
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	return "" if allowed("sales", user) and frappe.has_permission("Sales Order", "read", user=user) else "1=0"


def _order(name):
	from illumenate_lighting.illumenate_lighting.portal.order_review import lock_orders

	if not load_accessible_sales_order(name):
		frappe.throw("Order unavailable", frappe.PermissionError)
	lock_orders(name)
	order = load_accessible_sales_order(name)
	if not order:
		frappe.throw("Order unavailable", frappe.PermissionError)
	return order


def fork_schedule(order, purpose):
	"""Copy customer intent, with current engineering review required before resale."""
	from illumenate_lighting.illumenate_lighting.portal.access import can_edit_schedule
	from illumenate_lighting.illumenate_lighting.portal.configuration_reopen import for_line
	from illumenate_lighting.illumenate_lighting.portal.line_documents import clone

	if not order.get("ill_fixture_schedule"):
		frappe.throw("This historical order has no source schedule. Ask Sales to prepare a new request.")
	source = frappe.get_doc("ilL-Project-Fixture-Schedule", order.ill_fixture_schedule)
	if not can_edit_schedule(source):
		frappe.throw("Schedule edit access is required to create a new draft", frappe.PermissionError)
	frappe.db.sql("select name from `tabilL-Project-Fixture-Schedule` where name=%s for update", source.name)
	source.reload()
	if not can_edit_schedule(source):
		frappe.throw("Schedule access changed", frappe.PermissionError)
	draft = frappe.new_doc(source.doctype)
	for field in ("ill_project", "customer", "inherits_project_privacy", "is_private", "notes", "project"):
		draft.set(field, source.get(field))
	draft.schedule_name = f"{purpose}: {source.schedule_name}"[:140]
	draft.status, draft.version = "DRAFT", 1
	draft.version_notes = f"{purpose} of {order.name}. Reconfigure each configured line with current specifications; prices are recalculated before a new request."
	exclude = {
		"name",
		"idx",
		"parent",
		"parenttype",
		"parentfield",
		"doctype",
		"creation",
		"modified",
		"modified_by",
		"owner",
	}
	for line in source.lines:
		values = {key: value for key, value in line.as_dict().items() if key not in exclude}
		configured = any(
			values.get(key)
			for key in (
				"configured_group",
				"configured_fixture",
				"configured_tape_neon",
				"configured_led_sheet",
			)
		)
		# Older kit/tape rows can carry generated artifacts only inside selection JSON.
		configured = configured or bool(
			values.get("variant_selections") and values.get("manufacturer_type") == "ILLUMENATE"
		)
		if configured:
			request = for_line(line)
			values["ill_configurator_request"] = canonical_json(request) if request else None
			# Only intent survives a reorder. Legacy selection JSON may contain
			# generated Item/BOM links that would bypass current engineering.
			values["variant_selections"] = None
			values["configuration_status"] = "Pending"
			for key in (
				"configured_group",
				"configured_fixture",
				"configured_tape_neon",
				"configured_led_sheet",
				"ill_item_code",
				"item_code",
				"bom_no",
				"ill_bom",
				"unit_price",
				"extended_price",
				"manufacturable_length_mm",
				"total_watts",
				"total_lumens",
				"manufacturable_length_in",
			):
				if key in values:
					values[key] = None
			values["notes"] = (
				(values.get("notes") or "")
				+ "\nReconfigure this line against current engineering and pricing before requesting an order."
			).strip()
		draft.append("lines", values)
	for row in source.collaborators or []:
		draft.append(
			"collaborators", {key: value for key, value in row.as_dict().items() if key not in exclude}
		)
	draft.insert(ignore_permissions=True)
	for old, new in zip(source.lines, draft.lines, strict=True):
		clone(source.name, old, draft.name, new)
	return draft.name


@frappe.whitelist(methods=["POST"])
@atomic_build
def submit(order_name, request_type, note, revision_hash, idempotency_key, file_ids=None):
	from illumenate_lighting.illumenate_lighting.portal.files import finalize_files

	order = _order(order_name)
	_buyer(order.customer)
	if request_type not in TYPES or not isinstance(note, str) or not note.strip() or len(note) > 4000:
		frappe.throw("Choose a request type and explain the request in up to 4,000 characters")
	if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 128:
		frappe.throw("A retry key is required")
	files = json.loads(file_ids) if isinstance(file_ids, str) else (file_ids or [])
	if not isinstance(files, list) or len(files) > 10 or any(not isinstance(value, str) for value in files):
		frappe.throw("Choose at most 10 uploaded files")
	data = {
		"type": request_type,
		"note": note.strip(),
		"revision": revision_hash,
		"files": sorted(set(files)),
	}
	key = fingerprint({"actor": frappe.session.user, "order": order_name, "key": idempotency_key})
	old = frappe.db.get_value(
		DOCTYPE, {"request_key": key}, ["name", "request_hash", "new_schedule"], as_dict=True
	)
	if old:
		if old.request_hash != fingerprint(data):
			frappe.throw("This retry key was already used for different content")
		return {"success": True, "name": old.name, "new_schedule": old.new_schedule, "already_existed": True}
	current = snapshot(order)
	if fingerprint(current) != revision_hash:
		frappe.throw("The order changed. Reload and review before requesting a change.")
	if request_type in ("Change", "Cancellation", "Reorder") and order.docstatus != 1:
		frappe.throw("This action requires an approved order. Use the pending request review instead.")
	if request_type == "Replacement":
		state = frappe.db.get_value("ilL-Order-Intake", {"sales_order": order.name}, "state")
		if order.docstatus != 2 and state not in ("REJECTED", "WITHDRAWN"):
			frappe.throw("Replacement is available after rejection, withdrawal or cancellation")
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"sales_order": order.name,
			"customer": order.customer,
			"requested_by": frappe.session.user,
			"request_type": request_type,
			"note": note.strip(),
			"state": "SUBMITTED",
			"request_key": key,
			"request_hash": fingerprint(data),
			"original_snapshot": canonical_json(current),
			"original_hash": revision_hash,
			"ill_next_action_by": "Staff",
		}
	)
	doc.flags.order_change_service = True
	doc.insert(ignore_permissions=True)
	finalize_files(files, DOCTYPE, doc.name, allow_unbound=True)
	if request_type in ("Reorder", "Replacement"):
		doc.new_schedule = fork_schedule(order, request_type)
		doc.state, doc.ill_next_action_by = "COMPLETED", "Customer"
		doc.staff_note = "New draft created. Current engineering and price review are required."
		doc.save(ignore_permissions=True)
	return {"success": True, "name": doc.name, "new_schedule": doc.get("new_schedule")}


@frappe.whitelist()
def review_context(name):
	doc = frappe.get_doc(DOCTYPE, name)
	order = load_accessible_sales_order(doc.sales_order)
	if not order:
		frappe.throw("Order unavailable", frappe.PermissionError)
	_staff(order)
	current, original = snapshot(order), json.loads(doc.original_snapshot)
	return {
		"expected_modified": str(doc.modified),
		"revision_hash": fingerprint(current),
		"order_docstatus": order.docstatus,
		"changes": {
			key: {"before": original.get(key), "after": current.get(key)}
			for key in current
			if original.get(key) != current.get(key)
		},
	}


@frappe.whitelist(methods=["POST"])
@atomic_build
def decide(name, action, note, expected_modified, revision_hash, result_sales_order=None):
	from illumenate_lighting.illumenate_lighting.portal.order_review import lock_orders

	doc = frappe.get_doc(DOCTYPE, name)
	lock_orders(doc.sales_order, result_sales_order)
	order = _order(doc.sales_order)
	_staff(order, approve=action == "COMPLETE")
	frappe.db.sql("select name from `tabilL-Order-Change` where name=%s for update", name)
	doc.reload()
	if doc.state in ("COMPLETED", "REJECTED"):
		frappe.throw("This request has already been decided")
	current = snapshot(order)
	if str(doc.modified) != str(expected_modified) or fingerprint(current) != revision_hash:
		frappe.throw("The request or order changed. Reload the comparison before deciding.")
	if (
		action not in ("REVIEW", "REJECT", "COMPLETE")
		or not isinstance(note, str)
		or not note.strip()
		or len(note) > 4000
	):
		frappe.throw("Choose a decision and explain the outcome in up to 4,000 characters")
	if action == "COMPLETE":
		if doc.request_type == "Cancellation" and order.docstatus != 2:
			frappe.throw(
				"Cancel the Sales Order using the native ERP workflow before completing this request"
			)
		if doc.request_type == "Change":
			if not result_sales_order:
				frappe.throw("Provide the approved amended Sales Order that implements this change")
			amended = _order(result_sales_order)
			if (
				not amended
				or amended.customer != order.customer
				or amended.docstatus != 1
				or amended.get("amended_from") != order.name
				or order.docstatus != 2
			):
				frappe.throw("The result must be an approved amendment of this cancelled Sales Order")
			intake = frappe.db.get_value(
				"ilL-Order-Intake",
				{"sales_order": amended.name},
				["name", "state", "approved_snapshot"],
				as_dict=True,
			)
			if not intake or intake.state != "APPROVED":
				frappe.throw("The amended order must complete buyer acknowledgment and staff approval")
			if not intake.approved_snapshot or fingerprint(
				json.loads(intake.approved_snapshot)
			) != fingerprint(snapshot(amended)):
				frappe.throw(
					"The amended order differs from its approved acknowledgment; reconcile it before completing the change"
				)
			doc.result_sales_order = amended.name
			current = snapshot(amended)
	doc.state = {"REVIEW": "UNDER_REVIEW", "REJECT": "REJECTED", "COMPLETE": "COMPLETED"}[action]
	doc.staff_note, doc.decided_by, doc.decided_on = note.strip(), frappe.session.user, frappe.utils.now()
	doc.result_snapshot, doc.ill_next_action_by = (
		canonical_json(current),
		"None" if action != "REVIEW" else "Staff",
	)
	doc.flags.order_change_service = True
	doc.save(ignore_permissions=True)
	from illumenate_lighting.illumenate_lighting.portal.notifications import notify_user

	notify_user(
		doc.requested_by,
		"notify_orders",
		f"Order request {doc.name}: {doc.state}",
		f'<p><a href="/portal/orders/{frappe.utils.escape_html(order.name)}">Review the order request outcome</a>.</p>',
		reference_doctype=DOCTYPE,
		reference_name=doc.name,
		event_key=f"{doc.name}:{doc.modified}",
	)
	return {"success": True, "state": doc.state}


def list_for_order(order_name):
	if not load_accessible_sales_order(order_name):
		frappe.throw("Order unavailable", frappe.PermissionError)
	return frappe.get_all(
		DOCTYPE,
		filters={"sales_order": order_name},
		fields=[
			"name",
			"request_type",
			"note",
			"state",
			"staff_note",
			"new_schedule",
			"result_sales_order",
			"creation",
			"decided_on",
		],
		order_by="creation desc, name desc",
		limit_page_length=50,
	)
