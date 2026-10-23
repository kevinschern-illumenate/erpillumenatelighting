"""One native permission-aware query for each staff queue and its count."""

from copy import deepcopy

import frappe

from illumenate_lighting.illumenate_lighting.portal.conversations import _pagination
from illumenate_lighting.illumenate_lighting.portal.staff import allowed
from illumenate_lighting.illumenate_lighting.portal.status import SALES_EMAIL

# (label, capability, DocType, base filters, projected fields, owner, due date)
QUEUES = {
	"verification": (
		"Product verification",
		"sales",
		"ilL-Product-Verification-Request",
		{"state": ["in", ["REQUESTED", "UNDER_REVIEW", "INFORMATION_NEEDED"]]},
		["name", "product_title", "customer", "state", "assigned_to", "due_date", "modified"],
		"assigned_to",
		"due_date",
	),
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
		[
			"name",
			"customer",
			"project",
			"schedule",
			"requested_by",
			"state",
			"assigned_to",
			"due_date",
			"modified",
		],
		"assigned_to",
		"due_date",
	),
	"expiring_offers": (
		"Offers expiring soon",
		"sales",
		"ilL-Quote-Offer",
		{"state": "ISSUED"},
		["name", "customer", "schedule", "quotation", "valid_until", "issued_by", "modified"],
		None,
		None,
	),
	"orders": (
		"Order review",
		"sales",
		"ilL-Order-Intake",
		{"state": ["in", ["SUBMITTED", "UNDER_REVIEW", "INFORMATION_NEEDED", "CHANGES_PROPOSED"]]},
		[
			"name",
			"sales_order",
			"customer",
			"schedule",
			"requested_by",
			"state",
			"assigned_to",
			"due_date",
			"modified",
		],
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
	"materials": (
		"Materials to order",
		"operations",
		"Material Request",
		{
			"docstatus": 1,
			"material_request_type": "Purchase",
			"status": ["in", ["Pending", "Partially Ordered"]],
		},
		["name", "transaction_date", "schedule_date", "status", "per_ordered", "modified"],
		None,
		"schedule_date",
	),
	"inbox": (
		"Sales inbox",
		"inbox",
		"Communication",
		{
			"communication_type": "Communication",
			"communication_medium": "Email",
			"sent_or_received": "Received",
			"status": "Open",
			"reference_doctype": ["is", "not set"],
			"recipients": ["like", "%" + SALES_EMAIL + "%"],
		},
		["name", "subject", "sender", "communication_date", "_assign", "modified"],
		"_assign",
		None,
	),
	"new_customers": (
		"New customers to set up",
		"accounts",
		"Customer",
		{"disabled": 0, "crm_deal": ["is", "set"], "payment_terms": ["is", "not set"]},
		["name", "customer_name", "crm_deal", "customer_group", "creation", "modified"],
		None,
		None,
	),
	"bills": (
		"Bills not in QuickBooks",
		"accounts",
		"Purchase Invoice",
		{"docstatus": 1, "is_return": 0, "custom_qbo_id": ["is", "not set"]},
		["name", "supplier", "bill_no", "posting_date", "grand_total", "modified"],
		None,
		None,
	),
}

# Due fields holding a date (not a datetime) compare against today's date.
DATE_DUE_FIELDS = ("due_date", "schedule_date")

# Desk assignment (a JSON list of users) can only answer "mine".
ASSIGN_FIELD = "_assign"

# Queues that read a field another app adds; they stay hidden until it exists.
# Customer.crm_deal comes with ERPNext's Frappe CRM synchronization.
REQUIRED_FIELDS = {"new_customers": ("Customer", "crm_deal")}

# Queues whose filters depend on site settings. Each returns extra filters, or None to hide the queue.
DYNAMIC_FILTERS = {
	"bills": "illumenate_lighting.illumenate_lighting.api.qbo_bills.queue_filters",
	"expiring_offers": "illumenate_lighting.illumenate_lighting.portal.offers.expiring_queue_filters",
}

# Queues whose document names are hashes or codes search a readable field instead.
SEARCH_FIELDS = {"inbox": "subject", "new_customers": "customer_name"}


def _views(owner, due):
	views = ["all"]
	if owner == ASSIGN_FIELD:
		views.append("mine")
	elif owner:
		views += ["mine", "unassigned"]
	return views + (["overdue"] if due else [])


def _queue_allowed(queue, capability):
	if queue == "verification":
		from illumenate_lighting.illumenate_lighting.portal.product_finder.verification import staff

		return staff()
	if queue in REQUIRED_FIELDS:
		doctype, fieldname = REQUIRED_FIELDS[queue]
		if not frappe.get_meta(doctype).has_field(fieldname):
			return False
	if _dynamic_filters(queue) is None:
		return False
	return allowed(capability)


def _dynamic_filters(queue):
	if queue not in DYNAMIC_FILTERS:
		return {}
	return frappe.get_attr(DYNAMIC_FILTERS[queue])()


def query(queue, view="all", search=None):
	if queue not in QUEUES:
		frappe.throw("Unknown staff queue")
	label, capability, doctype, filters, fields, owner, due = QUEUES[queue]
	if not _queue_allowed(queue, capability) or not frappe.has_permission(doctype, "read"):
		frappe.throw("This staff queue is unavailable for your role", frappe.PermissionError)
	filters = deepcopy(filters)
	filters.update(_dynamic_filters(queue))
	if view not in _views(owner, due):
		frappe.throw("This queue does not support that view")
	if view == "mine" and owner == ASSIGN_FIELD:
		filters[owner] = ["like", '%"' + frappe.session.user + '"%']
	elif view == "mine":
		filters[owner] = frappe.session.user
	elif view == "unassigned":
		filters[owner] = ["is", "not set"]
	elif view == "overdue":
		filters[due] = ["<", frappe.utils.nowdate() if due in DATE_DUE_FIELDS else frappe.utils.now()]
	if search:
		filters[SEARCH_FIELDS.get(queue, "name")] = ["like", "%" + str(search)[:100] + "%"]
	return label, doctype, filters, fields


def _count(doctype, filters):
	# get_list applies the same native permissions and query conditions as rows.
	# Frappe v16 rejects SQL functions written as strings, so the count uses dict syntax.
	rows = frappe.get_list(
		doctype,
		filters=filters,
		fields=[{"COUNT": "name", "as": "total"}],
		order_by=None,
		limit_page_length=1,
	)
	return int(rows[0].get("total") or 0) if rows else 0


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
		if not _queue_allowed(key, capability):
			continue
		entry = {
			"key": key,
			"label": label,
			"group": capability,
			"views": _views(owner, due),
		}
		try:
			_, doctype, filters, _ = query(key)
			entry.update(total=_count(doctype, filters), available=True)
		except frappe.PermissionError:
			entry.update(available=False, error="Native document read permission is required")
		result.append(entry)
	return {"queues": result}
