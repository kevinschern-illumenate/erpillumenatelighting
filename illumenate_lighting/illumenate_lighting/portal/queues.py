"""One native permission-aware query for each staff queue and its count."""

from copy import deepcopy

import frappe

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
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


# One staff inbox over every queue whose records carry an owner (plan 7.4). Drawing reapproval and
# manufacturing holds are subsets of open drawing requests, so a record appears once.
INBOX_QUEUES = (
	"quotes",
	"orders",
	"order_changes",
	"verification",
	"accounts",
	"drawings",
	"reapproval",
	"production",
	"support",
)
INBOX_LIMIT = 100
DUE_SOON_HOURS = 24
DUE_ORDER = {"overdue": 0, "due_soon": 1, "ok": 2, "none": 3}
# Who the record is for: a customer when it has one, else the dealer user who raised it.
DEALER_FIELDS = {
	"ilL-Document-Request": ("requester_user",),
	"Issue": ("customer", "raised_by"),
}
DEFAULT_DEALER_FIELDS = ("customer", "requested_by")


def due_state(value, due_field, now=None):
	"""overdue, due_soon (a date due today, or a datetime within a day), ok, or none."""
	if not value:
		return "none"
	utils = frappe.utils
	now = utils.get_datetime(now or utils.now_datetime())
	if due_field in DATE_DUE_FIELDS:
		due, today = utils.getdate(value), now.date()
		return "overdue" if due < today else "due_soon" if due == today else "ok"
	due = utils.get_datetime(value)
	if due < now:
		return "overdue"
	return "due_soon" if due <= utils.add_to_date(now, hours=DUE_SOON_HOURS) else "ok"


def _age_days(value, now):
	if not value:
		return None
	return max(0, (now - frappe.utils.get_datetime(value)).days)


def _customer_names(rows):
	names = sorted({row["customer"] for row in rows if row.get("customer")})
	if not names:
		return {}
	return {
		row.name: row.customer_name or row.name
		for row in frappe.get_all(
			"Customer", filters={"name": ["in", names]}, fields=["name", "customer_name"]
		)
	}


def _inbox_rows(key, view, search, now):
	from illumenate_lighting.illumenate_lighting.portal.conversations import CLOSED, PARENTS

	owner, due = QUEUES[key][5], QUEUES[key][6]
	label, doctype, filters, fields = query(key, view, search)
	dealer = DEALER_FIELDS.get(doctype, DEFAULT_DEALER_FIELDS)
	rows = frappe.get_list(
		doctype,
		filters=filters,
		fields=list(dict.fromkeys([*fields, *dealer, "creation"])),
		order_by="modified asc, name asc",
		limit_page_length=INBOX_LIMIT + 1,
	)
	result = []
	for row in rows[:INBOX_LIMIT]:
		state = row.get("state") or row.get("ill_review_state") or row.get("status")
		result.append(
			{
				"queue": key,
				"queue_label": label,
				"doctype": doctype,
				"name": row.get("name"),
				"title": row.get("product_title") or row.get("subject") or row.get("request_type"),
				"customer": row.get("customer"),
				"dealer_user": next(
					(row.get(field) for field in dealer if field != "customer" and row.get(field)), None
				),
				"assigned_to": row.get(owner),
				"due": str(row.get(due)) if due and row.get(due) else None,
				"due_state": due_state(row.get(due), due, now) if due else "none",
				"age_days": _age_days(row.get("creation"), now),
				"state": state,
				"next_action_by": row.get("ill_next_action_by"),
				"modified": str(row.get("modified")),
				"can_wait": doctype in PARENTS and state not in CLOSED,
			}
		)
	return result, len(rows) > INBOX_LIMIT


@frappe.whitelist()
def inbox(view="all", search=None):
	"""Every owned staff work item the user may read, overdue first (plan 7.4).

	Each queue goes through ``query``, so roles, native read permission and open-state filters are
	exactly those of the queue tiles. Queues that do not support ``view`` are skipped.
	"""
	if view not in ("all", "mine", "unassigned", "overdue"):
		frappe.throw("This queue does not support that view")
	now = frappe.utils.get_datetime(frappe.utils.now_datetime())
	rows, seen, truncated, queues = [], set(), [], []
	for key in INBOX_QUEUES:
		_label, capability, _doctype, _filters, _fields, owner, due = QUEUES[key]
		if view not in _views(owner, due) or not _queue_allowed(key, capability):
			continue
		try:
			found, more = _inbox_rows(key, view, search, now)
		except frappe.PermissionError:
			continue
		queues.append(key)
		if more:
			truncated.append(key)
		for row in found:
			marker = (row["doctype"], row["name"])
			if marker not in seen:
				seen.add(marker)
				rows.append(row)
	names = _customer_names(rows)
	for row in rows:
		row["customer_name"] = names.get(row["customer"]) if row["customer"] else None
	rows.sort(key=lambda row: (DUE_ORDER[row["due_state"]], row["due"] or "", -(row["age_days"] or 0)))
	return {"rows": rows, "total": len(rows), "queues": queues, "truncated": truncated, "view": view}


@frappe.whitelist(methods=["POST"])
@atomic_build
def claim(queue, name, expected_modified=None):
	"""Assign an inbox item to the current user through the same checks as the queue's own assign."""
	from illumenate_lighting.illumenate_lighting.portal import commercial_tasks

	if queue not in INBOX_QUEUES:
		frappe.throw("Unknown staff queue")
	_label, capability, doctype, _filters, _fields, owner, _due = QUEUES[queue]
	user = frappe.session.user
	if doctype in commercial_tasks.TYPES:
		# Keep the due date: commercial assign treats a blank due date as "clear it".
		due = None if doctype == "ilL-Account-Request" else frappe.db.get_value(doctype, name, "due_date")
		return {**commercial_tasks.assign(doctype, name, user, due, expected_modified), "assigned_to": user}
	if not _queue_allowed(queue, capability) or not frappe.has_permission(doctype, "write", doc=name):
		frappe.throw("Staff queue access required", frappe.PermissionError)
	frappe.db.sql(f"select name from `tab{doctype}` where name=%s for update", name)
	doc = frappe.get_doc(doctype, name)
	if str(doc.modified) != str(expected_modified):
		frappe.throw("This item changed. Reload before assigning it.")
	doc.set(owner, user)
	doc.save()
	return {"success": True, "modified": str(doc.modified), "assigned_to": user}
