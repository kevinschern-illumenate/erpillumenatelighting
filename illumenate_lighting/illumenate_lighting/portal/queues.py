"""One native permission-aware query for each staff queue and its count."""

from copy import deepcopy

import frappe

from illumenate_lighting.illumenate_lighting.portal.conversations import _pagination
from illumenate_lighting.illumenate_lighting.portal.staff import allowed

# (label, capability, DocType, base filters, projected fields, owner, due date)
QUEUES = {
	"order_changes": (
		"Order changes and cancellations",
		"sales",
		"ilL-Order-Change",
		{"state": ["in", ["SUBMITTED", "UNDER_REVIEW", "INFORMATION_NEEDED"]]},
		["name", "sales_order", "request_type", "state", "assigned_to", "due_date", "modified"],
		"assigned_to",
		"due_date",
	),
	"accounts": (
		"Account review",
		"accounts",
		"ilL-Account-Request",
		{"state": ["in", ["Pending", "Information needed"]]},
		["name", "request_type", "requested_by", "customer", "state", "assigned_to", "modified"],
		"assigned_to",
		None,
	),
	"quotes": (
		"Quote requests",
		"sales",
		"ilL-Quote-Request",
		{"state": ["in", ["REQUESTED", "UNDER_REVIEW", "INFORMATION_NEEDED"]]},
		["name", "state", "assigned_to", "due_date", "modified"],
		"assigned_to",
		"due_date",
	),
	"orders": (
		"Order review",
		"sales",
		"ilL-Order-Intake",
		{"state": ["in", ["SUBMITTED", "UNDER_REVIEW", "INFORMATION_NEEDED", "CHANGES_PROPOSED"]]},
		["name", "sales_order", "state", "assigned_to", "due_date", "modified"],
		"assigned_to",
		"due_date",
	),
	"drawings": (
		"Drawing responses",
		"engineering",
		"ilL-Document-Request",
		{"status": ["not in", ["Completed", "Closed", "Cancelled"]]},
		[
			"name",
			"status",
			"ill_review_state",
			"ill_next_action_by",
			"assigned_to",
			"sla_deadline",
			"modified",
		],
		"assigned_to",
		"sla_deadline",
	),
	"reapproval": (
		"Drawing reapproval",
		"engineering",
		"ilL-Document-Request",
		{"ill_review_state": ["in", ["Reapproval required", "Changes requested"]]},
		["name", "ill_review_state", "assigned_to", "sla_deadline", "ill_impact_task", "modified"],
		"assigned_to",
		"sla_deadline",
	),
	"support": (
		"Support responses",
		"support",
		"Issue",
		{"status": ["not in", ["Resolved", "Closed"]]},
		[
			"name",
			"subject",
			"status",
			"ill_next_action_by",
			"ill_support_owner",
			"ill_support_due",
			"modified",
		],
		"ill_support_owner",
		"ill_support_due",
	),
	"exports": (
		"Incomplete exports",
		"engineering",
		"ilL-Export-Job",
		{"status": ["in", ["FAILED", "INCOMPLETE"]]},
		["name", "schedule", "export_type", "status", "modified"],
		None,
		None,
	),
	"publication": (
		"Publication failures",
		"integration",
		"ilL-Publish-Job",
		{"state": "FAILED"},
		["name", "product", "brand", "operation", "state", "modified"],
		None,
		None,
	),
	"email": (
		"Email failures",
		"integration",
		"ilL-Portal-Delivery",
		{"state": "FAILED"},
		["name", "event", "state", "detail", "modified"],
		None,
		None,
	),
	"production": (
		"Manufacturing drawing holds",
		"operations",
		"ilL-Document-Request",
		{"required_for_manufacturing": 1, "ill_review_state": ["!=", "Approved"]},
		["name", "sales_order", "ill_review_state", "assigned_to", "sla_deadline", "modified"],
		"assigned_to",
		"sla_deadline",
	),
}


def query(queue, view="all", search=None):
	if queue not in QUEUES:
		frappe.throw("Unknown staff queue")
	label, capability, doctype, filters, fields, owner, due = QUEUES[queue]
	if not allowed(capability) or not frappe.has_permission(doctype, "read"):
		frappe.throw("This staff queue is unavailable for your role", frappe.PermissionError)
	filters = deepcopy(filters)
	if view == "mine" and owner:
		filters[owner] = frappe.session.user
	elif view == "unassigned" and owner:
		filters[owner] = ["is", "not set"]
	elif view == "overdue" and due:
		filters[due] = ["<", frappe.utils.nowdate() if due == "due_date" else frappe.utils.now()]
	elif view != "all":
		frappe.throw("This queue does not support that view")
	if search:
		filters["name"] = ["like", "%" + str(search)[:100] + "%"]
	return label, doctype, filters, fields


def _count(doctype, filters):
	# get_list applies the same native permissions and query conditions as rows.
	rows = frappe.get_list(doctype, filters=filters, fields=["count(name) as total"], limit_page_length=1)
	return int(rows[0].get("total", 0)) if rows else 0


@frappe.whitelist()
def items(queue, view="all", search=None, page=1, page_size=20):
	page, page_size = _pagination(page, page_size)
	label, doctype, filters, fields = query(queue, view, search)
	return {
		"label": label,
		"doctype": doctype,
		"total": _count(doctype, filters),
		"page": page,
		"page_size": page_size,
		"rows": frappe.get_list(
			doctype,
			filters=filters,
			fields=fields,
			order_by="modified asc, name asc",
			limit_start=(page - 1) * page_size,
			limit_page_length=page_size,
		),
	}


@frappe.whitelist()
def summary():
	result = []
	for key, (label, capability, doctype, _filters, _fields, owner, due) in QUEUES.items():
		if not allowed(capability):
			continue
		entry = {
			"key": key,
			"label": label,
			"views": ["all"] + (["mine", "unassigned"] if owner else []) + (["overdue"] if due else []),
		}
		try:
			_, doctype, filters, _ = query(key)
			entry.update(total=_count(doctype, filters), available=True)
		except frappe.PermissionError:
			entry.update(available=False, error="Native document read permission is required")
		result.append(entry)
	return {"queues": result}
