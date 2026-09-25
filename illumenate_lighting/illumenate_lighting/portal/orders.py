# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal order read model and commands.

Everything the portal shows about a Sales Order comes from here so the
dashboard, the orders list and the order detail page derive the same
customer-facing status from the same authoritative ERP facts (Sales Order,
Work Order quantities, Delivery Notes, Sales Invoices).
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from illumenate_lighting.illumenate_lighting.portal.access import get_actor
from illumenate_lighting.illumenate_lighting.portal.status import (
	derive_order_portal_status,
	order_status_class,
	order_status_label,
	order_status_progress,
)

# Delivery Note fields maintained operationally for carrier / tracking
# (product decision: vehicle_no carries the tracking number).
DELIVERY_CARRIER_FIELD = "transporter_name"
DELIVERY_TRACKING_FIELD = "vehicle_no"

DOWNLOADABLE_DOCTYPES = {
	"Sales Order": {"print_format": "ilL Sales Order", "label": "Order"},
	"Sales Invoice": {"print_format": "ilL Sales Invoice", "label": "Invoice"},
	"Delivery Note": {"print_format": None, "label": "Packing Slip"},
}

PO_NUMBER_MAX_LENGTH = 140


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------


def load_accessible_sales_order(order_name, user=None):
	"""Return the Sales Order if ``user`` may see it, else ``None``.

	Orders carry dealer pricing, so only Dealers of the ordering Customer and
	internal users may open them. Cancelled orders stay visible so the audit
	trail is honest.
	"""
	if not order_name or not frappe.db.exists("Sales Order", order_name):
		return None
	actor = get_actor(user)
	if actor.is_guest:
		return None
	order = frappe.get_doc("Sales Order", order_name)
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if actor.is_internal or (allowed("sales", actor.user) and frappe.has_permission("Sales Order", "read", doc=order, user=actor.user)):
		return order
	if actor.is_dealer and actor.customer and order.customer == actor.customer:
		return order
	return None


def _customer_document_accessible(doc, actor):
	if actor.is_internal:
		return True
	return bool(actor.is_dealer and actor.customer) and doc.get("customer") == actor.customer


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def _work_orders_for(order_names):
	if not order_names:
		return {}
	rows = frappe.get_all(
		"Work Order",
		filters={"sales_order": ["in", list(order_names)], "docstatus": 1},
		fields=[
			"name",
			"sales_order",
			"sales_order_item",
			"production_item",
			"status",
			"qty",
			"produced_qty",
			"planned_start_date",
			"actual_start_date",
			"actual_end_date",
			"expected_delivery_date",
		],
		order_by="creation asc",
	)
	by_order = {}
	for row in rows:
		by_order.setdefault(row.sales_order, []).append(row)
	return by_order


def _shipments_for(order_name):
	parents = frappe.get_all(
		"Delivery Note Item",
		filters={"against_sales_order": order_name, "docstatus": 1},
		distinct=True,
		pluck="parent",
	)
	shipments = []
	for name in parents:
		dn = frappe.get_doc("Delivery Note", name)
		shipments.append(
			{
				"name": dn.name,
				"posting_date": dn.posting_date,
				"status": dn.status,
				"is_return": bool(dn.get("is_return")),
				"return_against": dn.get("return_against"),
				"carrier": dn.get(DELIVERY_CARRIER_FIELD),
				"tracking_number": dn.get(DELIVERY_TRACKING_FIELD),
				# Legacy keys kept for existing templates.
				"transporter": dn.get(DELIVERY_CARRIER_FIELD),
				"tracking_no": dn.get(DELIVERY_TRACKING_FIELD),
				"items": [
					{"line": i.get("so_detail"), "item_code": i.item_code, "item_name": i.item_name, "qty": i.qty, "uom": i.uom,
					 "stock_qty": i.get("stock_qty") or flt(i.qty) * flt(i.get("conversion_factor") or 1)}
					for i in dn.items
					if i.against_sales_order == order_name
				],
			}
		)
	shipments.sort(key=lambda s: (s["posting_date"] or "", s["name"]))
	return shipments


def _invoices_for(order_name):
	names = frappe.get_all(
		"Sales Invoice Item",
		filters={"sales_order": order_name, "docstatus": 1},
		distinct=True,
		pluck="parent",
	)
	if not names:
		return []
	return frappe.get_all(
		"Sales Invoice",
		filters={"name": ["in", names], "docstatus": 1},
		fields=[
			"name",
			"posting_date",
			"due_date",
			"status",
			"grand_total",
			"outstanding_amount",
			"is_return",
			"return_against",
			"currency",
		],
		order_by="posting_date asc, name asc",
	)


def _production_summary(work_orders, order_lines=()):
	from illumenate_lighting.illumenate_lighting.portal.production import production_coverage

	coverage = production_coverage(order_lines, work_orders)
	total = sum(flt(w.get("qty")) for w in work_orders)
	produced = sum(flt(w.get("produced_qty")) for w in work_orders)
	started = [w.get("actual_start_date") for w in work_orders]
	started = [d for d in started if d]
	return {
		"work_order_count": len(work_orders),
		"planned_qty": total,
		"produced_qty": produced,
		"percent": round(produced / total * 100, 1) if total else 0,
		"started_on": min(started) if started else None,
		"completed": coverage["complete"],
		"coverage": coverage,
	}


# ---------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------


def _decorate(order_row, work_orders, order_lines=()):
	production = _production_summary(work_orders, order_lines)
	key = derive_order_portal_status(
		docstatus=cint(order_row.get("docstatus")),
		erp_status=order_row.get("status"),
		per_delivered=order_row.get("per_delivered"),
		per_billed=order_row.get("per_billed"),
		work_orders=work_orders,
		production_complete=production["completed"],
	)
	order_row["erp_status"] = order_row.get("status")
	order_row["portal_status"] = key
	order_row["portal_status_label"] = order_status_label(key)
	order_row["portal_status_class"] = order_status_class(key)
	order_row["progress_percent"] = order_status_progress(key)
	order_row["is_request"] = cint(order_row.get("docstatus")) == 0
	order_row["is_cancelled"] = cint(order_row.get("docstatus")) == 2
	order_row["production"] = production
	order_row["production_started"] = bool(work_orders) and (
		order_row["production"]["produced_qty"] > 0
		or any(w.get("status") in ("In Process", "Completed") for w in work_orders)
	)
	order_row["production_complete"] = order_row["production"]["completed"]
	return order_row


def list_orders(user=None, *, page=None, page_size=20, search=None, status=None):
	"""Orders the portal user may see, newest first, with portal status."""
	actor = get_actor(user)
	if actor.is_guest:
		return []

	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	staff_reader = allowed("sales", actor.user) and frappe.has_permission("Sales Order", "read", user=actor.user)
	filters = {}
	if not actor.is_internal and not staff_reader:
		if not (actor.is_dealer and actor.customer):
			return []
		filters["customer"] = actor.customer

	states = {
		"all": {}, "requests": {"docstatus": 0},
		"active": {"docstatus": 1, "per_delivered": ["<", 100]},
		"shipping": {"docstatus": 1, "per_delivered": ["between", [0.000001, 99.999999]]},
		"fulfilled": {"docstatus": 1, "per_delivered": [">=", 100]},
		"cancelled": {"docstatus": 2},
	}
	if (status or "all") not in states:
		frappe.throw("Choose a supported order filter")
	filters.update(states[status or "all"])
	query = str(search or "").strip()[:140]
	options = {"filters": filters, "user": actor.user, "limit_page_length": 0}
	if query:
		options["or_filters"] = {key: ["like", "%" + query + "%"] for key in ("name", "po_no", "customer_name")}
	if page is not None:
		from illumenate_lighting.illumenate_lighting.portal.conversations import _pagination

		page, page_size = _pagination(page, page_size)
		options.update(limit_start=(page - 1) * page_size, limit_page_length=page_size + 1)
	# Native query permissions apply as well as the explicit company boundary.
	orders = frappe.get_list(
		"Sales Order",
		**options,
		fields=[
			"name",
			"customer",
			"customer_name",
			"transaction_date",
			"delivery_date",
			"ill_requested_delivery_date",
			"ill_confirmed_delivery_date",
			"status",
			"grand_total",
			"currency",
			"total_qty",
			"po_no",
			"per_delivered",
			"per_billed",
			"docstatus",
			"ill_fixture_schedule",
		],
		order_by="creation desc, name desc",
	)
	work_orders = _work_orders_for([o.name for o in orders])
	lines = frappe.get_all("Sales Order Item", filters={"parent": ["in", [o.name for o in orders]]},
		fields=["name", "parent", "item_code", "qty", "conversion_factor", "ill_configured_fixture",
			"ill_configured_tape_neon", "ill_configured_led_sheet", "ill_configured_group", "ill_bom"]) if orders else []
	by_order = {}
	for line in lines:
		by_order.setdefault(line.parent, []).append(line)
	intakes = frappe.get_all("ilL-Order-Intake", filters={"sales_order": ["in", [o.name for o in orders]]}, fields=["sales_order", "state"]) if orders else []
	intake_states = {row.sales_order: row.state for row in intakes}
	for order in orders:
		_decorate(order, work_orders.get(order.name, []), by_order.get(order.name, []))
		_apply_intake_state(order, intake_states.get(order.name))
	return orders



def _apply_intake_state(head, state):
	head["intake_state"] = state
	if head.get("docstatus") == 0 and state in ("REJECTED", "WITHDRAWN"):
		head["is_request"] = False
		head.update(portal_status="issue", portal_status_label="Request " + state.lower(), portal_status_class="danger", progress_percent=0)


@frappe.whitelist()
def search_orders(search=None, status="all", page=1, page_size=20):
	from illumenate_lighting.illumenate_lighting.portal.conversations import _pagination

	page, page_size = _pagination(page, page_size)
	rows = list_orders(page=page, page_size=page_size, search=search, status=status)
	return {"orders": rows[:page_size], "has_more": len(rows) > page_size, "page": page,
		"page_size": page_size, "search": str(search or "")[:140], "filter": status}


def get_order_read_model(order_name, user=None):
	"""Full, access-checked order model for the detail page and API."""
	order = load_accessible_sales_order(order_name, user)
	if order is None:
		return None

	actor = get_actor(user)
	work_orders = _work_orders_for([order.name]).get(order.name, [])
	from illumenate_lighting.illumenate_lighting.portal.production import production_coverage

	coverage = production_coverage([row.as_dict() for row in order.items], work_orders)
	produced_by_item = {row["line"]: row["produced_qty"] for row in coverage["lines"]}
	coverage_by_line = {row["line"]: row for row in coverage["lines"]}

	lines = []
	for item in order.items:
		lines.append(
			{
				"name": item.name,
				"item_code": item.item_code,
				"item_name": item.item_name,
				"description": item.description,
				"qty": item.qty,
				"uom": item.uom,
				"rate": item.rate,
				"amount": item.amount,
				"delivery_date": item.delivery_date,
				"delivered_qty": flt(item.get("delivered_qty")),
				"produced_qty": produced_by_item.get(item.name, 0),
				"planning_path": coverage_by_line[item.name]["path"],
				"open_qty": max(0, flt(item.qty) - flt(item.get("delivered_qty"))),
				"billed_amount": flt(item.get("billed_amt")),
				"section_room": item.get("ill_section_label"),
				"fixture_type": item.get("ill_fixture_type"),
				"customer_note": item.get("additional_notes"),
				"configured_fixture": item.get("ill_configured_fixture"),
			}
		)

	shipments = _shipments_for(order.name) if order.docstatus == 1 else []
	invoices = _invoices_for(order.name) if order.docstatus == 1 else []

	head = frappe._dict(
		{
			"name": order.name,
			"transaction_date": order.transaction_date,
			"delivery_date": order.delivery_date,
			"requested_date": order.get("ill_requested_delivery_date"),
			"confirmed_date": order.get("ill_confirmed_delivery_date"),
			"status": order.status,
			"docstatus": order.docstatus,
			"grand_total": order.grand_total,
			"total": order.total,
			"discount_amount": order.discount_amount,
			"total_taxes_and_charges": order.total_taxes_and_charges,
			"currency": order.currency,
			"customer": order.customer,
			"customer_name": order.customer_name,
			"po_no": order.po_no,
			"per_delivered": order.per_delivered,
			"per_billed": order.per_billed,
			"fixture_schedule": order.get("ill_fixture_schedule"),
			"remarks": order.remarks,
		}
	)
	_decorate(head, work_orders, [row.as_dict() for row in order.items])
	head["approved_on"] = frappe.db.get_value("ilL-Order-Intake", {"sales_order": order.name, "state": "APPROVED"}, "approved_on")
	from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint
	from illumenate_lighting.illumenate_lighting.portal.order_review import snapshot

	head["revision_hash"] = fingerprint(snapshot(order))
	_apply_intake_state(head, frappe.db.get_value("ilL-Order-Intake", {"sales_order": order.name}, "state"))
	# Customer-facing label; ERP status stays available as erp_status.
	head["status"] = head["portal_status_label"]

	schedule_info = None
	if head.fixture_schedule and frappe.db.exists(
		"ilL-Project-Fixture-Schedule", head.fixture_schedule
	):
		schedule_info = frappe.db.get_value(
			"ilL-Project-Fixture-Schedule",
			head.fixture_schedule,
			["name", "schedule_name", "ill_project", "status"],
			as_dict=True,
		)
		if schedule_info and schedule_info.ill_project:
			schedule_info["project_name"] = frappe.db.get_value(
				"ilL-Project", schedule_info.ill_project, "project_name"
			)

	can_manage = actor.is_internal or actor.is_dealer
	actions = {
		"can_set_po_number": order.docstatus == 0 and can_manage and head.get("intake_state") not in ("REJECTED", "WITHDRAWN"),
		"can_request_change": order.docstatus == 1 and actor.is_company_dealer_for(order.customer),
		"can_reorder": actor.is_company_dealer_for(order.customer),
		"downloads": [],
	}
	if order.docstatus < 2:
		actions["downloads"].append(
			{"doctype": "Sales Order", "name": order.name, "label": _("Order Request PDF") if order.docstatus == 0 else _("Order PDF")}
		)
	for inv in invoices:
		actions["downloads"].append(
			{"doctype": "Sales Invoice", "name": inv.name, "label": _("Invoice {0}").format(inv.name)}
		)
	for dn in shipments:
		actions["downloads"].append(
			{"doctype": "Delivery Note", "name": dn["name"], "label": _("Packing Slip {0}").format(dn["name"])}
		)

	timeline = _timeline(head, work_orders, shipments, invoices)

	return {
		"order": head,
		"lines": lines,
		"production": work_orders,
		"shipments": shipments,
		"invoices": invoices,
		"schedule": schedule_info,
		"timeline": timeline,
		"actions": actions,
	}


def _timeline(head, work_orders, shipments, invoices):
	events = [
		{
			"key": "requested",
			"label": _("Order Requested") if head.docstatus == 0 else _("Ordered"),
			"date": head.transaction_date,
			"done": True,
		}
	]
	events.append(
		{
			"key": "approved",
			"label": _("Approved"),
			"date": head.get("approved_on") if head.docstatus == 1 else None,
			"done": head.docstatus == 1,
		}
	)
	production = head.get("production") or {}
	events.append(
		{
			"key": "production",
			"label": _("In Production"),
			"date": production.get("started_on"),
			"done": bool(head.get("production_started")),
			"active": bool(head.get("production_started")) and not production.get("completed"),
		}
	)
	events.append(
		{
			"key": "shipped",
			"label": _("Shipped"),
			"date": next((row["posting_date"] for row in reversed(shipments) if not row.get("is_return")), None),
			"done": flt(head.per_delivered) >= 100,
			"active": 0 < flt(head.per_delivered) < 100,
		}
	)
	events.append(
		{
			"key": "completed",
			"label": _("Completed"),
			"date": invoices[-1].posting_date if invoices and head.portal_status == "completed" else None,
			"done": head.portal_status == "completed",
		}
	)
	if head.portal_status == "cancelled":
		events.append({"key": "cancelled", "label": _("Cancelled"), "date": None, "done": True})
	return events


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def set_order_request_po_number(order_name, po_no, user=None):
	"""Let the ordering Dealer record their PO number on a pending request."""
	actor = get_actor(user)
	order = load_accessible_sales_order(order_name, actor.user)
	if order is None:
		frappe.throw(_("Order not found"), frappe.PermissionError)
	if not (actor.is_internal or actor.is_dealer):
		frappe.throw(_("Only dealers can set a PO number on an order request"), frappe.PermissionError)
	frappe.db.sql("select name from `tabSales Order` where name=%s for update", order_name)
	order = load_accessible_sales_order(order_name, actor.user)
	if order is None:
		frappe.throw(_("Order not found"), frappe.PermissionError)
	if order.docstatus != 0:
		frappe.throw(_("The PO number can only be changed while the order request is awaiting approval"))

	po_no = (po_no or "").strip()[:PO_NUMBER_MAX_LENGTH]
	if po_no == (order.po_no or ""):
		return order

	from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint
	from illumenate_lighting.illumenate_lighting.portal.order_review import record_buyer_po_edit, snapshot

	previous_hash = fingerprint(snapshot(order))
	order.db_set("po_no", po_no or None)
	record_buyer_po_edit(order, previous_hash, actor.user)
	order.add_comment("Info", _("PO number set to {0} from the portal").format(po_no or _("(blank)")))
	return order


def get_order_document_pdf(doctype, name, user=None):
	"""Access-checked PDF for an order, invoice or packing slip.

	Returns ``(filename, pdf_bytes)``; raises ``frappe.PermissionError`` when
	the document is not the caller's.
	"""
	spec = DOWNLOADABLE_DOCTYPES.get(doctype)
	if not spec:
		frappe.throw(_("This document type cannot be downloaded"), frappe.PermissionError)

	actor = get_actor(user)
	if actor.is_guest or not name or not frappe.db.exists(doctype, name):
		frappe.throw(_("Document not found"), frappe.PermissionError)

	doc = frappe.get_doc(doctype, name)
	if not _customer_document_accessible(doc, actor):
		frappe.throw(_("Document not found"), frappe.PermissionError)
	if doctype == "Sales Order":
		if doc.docstatus == 2:
			frappe.throw(_("Document not found"), frappe.PermissionError)
	elif doc.docstatus != 1:
		frappe.throw(_("Document not found"), frappe.PermissionError)

	print_format = spec["print_format"]
	if print_format and not frappe.db.exists("Print Format", print_format):
		print_format = None

	# Access has been decided above against the customer link; portal roles
	# do not carry ERP print permissions on invoices / delivery notes.
	previous = frappe.flags.ignore_print_permissions
	frappe.flags.ignore_print_permissions = True
	try:
		pdf = frappe.get_print(doctype, name, print_format=print_format, as_pdf=True, doc=doc)
	finally:
		frappe.flags.ignore_print_permissions = previous

	filename = f"{spec['label'].replace(' ', '-')}-{name}.pdf"
	return filename, pdf
