# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal status vocabulary.

One mapping from internal schedule statuses and ERPNext order states to the
customer-facing labels, badge classes and explanations used across the portal
pages, so "Ready", "Order Request", "In Production" etc. mean the same thing
on the dashboard, the lists and the detail pages.
"""

from frappe import _

SALES_EMAIL = "sales@illumenate.lighting"

# --------------------------------------------------------------------------
# Fixture schedule statuses
# --------------------------------------------------------------------------

SCHEDULE_STATUS_META = {
	"DRAFT": {"label": "Draft", "css": "warning", "description": "Being configured"},
	"READY": {"label": "Ready", "css": "info", "description": "Ready for quote or order"},
	"QUOTED": {"label": "Quoted", "css": "primary", "description": "Quote provided"},
	"ORDER_REQUESTED": {
		"label": "Order Requested",
		"css": "info",
		"description": "Order request submitted and awaiting approval by ilLumenate",
	},
	"ORDERED": {"label": "Ordered", "css": "success", "description": "Order approved"},
	"ISSUE": {
		"label": "Issue",
		"css": "danger",
		"description": f"Please contact {SALES_EMAIL}",
	},
	"CLOSED": {"label": "Closed", "css": "secondary", "description": "Closed"},
}


def schedule_status_label(status):
	meta = SCHEDULE_STATUS_META.get(status)
	return _(meta["label"]) if meta else (status or "")


def schedule_status_class(status):
	meta = SCHEDULE_STATUS_META.get(status)
	return meta["css"] if meta else "secondary"


def schedule_status_description(status):
	meta = SCHEDULE_STATUS_META.get(status)
	return _(meta["description"]) if meta else ""


def schedule_status_map():
	"""Every schedule status with its label and badge class, for page scripts."""
	return {
		status: {"label": schedule_status_label(status), "css": meta["css"]}
		for status, meta in SCHEDULE_STATUS_META.items()
	}


# --------------------------------------------------------------------------
# Project statuses and export job statuses (UI-4)
# --------------------------------------------------------------------------

PROJECT_STATUS_META = {
	"ACTIVE": {"label": "Active", "css": "success"},
	"ON_HOLD": {"label": "On hold", "css": "warning"},
	"COMPLETED": {"label": "Completed", "css": "info"},
	"ARCHIVED": {"label": "Archived", "css": "secondary"},
}


def project_status_label(status):
	meta = PROJECT_STATUS_META.get(status)
	return _(meta["label"]) if meta else (status or "")


def project_status_class(status):
	meta = PROJECT_STATUS_META.get(status)
	return meta["css"] if meta else "secondary"


EXPORT_STATUS_META = {
	"QUEUED": {"label": "Queued", "css": "warning"},
	"RUNNING": {"label": "Generating", "css": "info"},
	"COMPLETE": {"label": "Ready", "css": "success"},
	"INCOMPLETE": {"label": "Ready with warnings", "css": "warning"},
	"FAILED": {"label": "Failed", "css": "danger"},
}


def export_status_map():
	return {
		status: {"label": _(meta["label"]), "css": meta["css"]} for status, meta in EXPORT_STATUS_META.items()
	}


VERIFICATION_STATUS_META = {
	"REQUESTED": {"label": "Received", "css": "info"},
	"UNDER_REVIEW": {"label": "Under review", "css": "info"},
	"INFORMATION_NEEDED": {"label": "Needs your reply", "css": "warning"},
	"VERIFIED": {"label": "Verified", "css": "success"},
	"NOT_FEASIBLE": {"label": "Not feasible", "css": "danger"},
	"CANCELLED": {"label": "Cancelled", "css": "secondary"},
}


def verification_status(state):
	"""(label, badge class) for a product verification request state."""
	meta = VERIFICATION_STATUS_META.get(state)
	return (_(meta["label"]), meta["css"]) if meta else (state or "", "secondary")


# --------------------------------------------------------------------------
# Sales Order -> customer-facing order status
# --------------------------------------------------------------------------

ORDER_PORTAL_STATUSES = {
	"order_request": {"label": "Order Request", "css": "warning", "progress": 5},
	"approved": {"label": "Approved", "css": "info", "progress": 15},
	"in_production": {"label": "In Production", "css": "primary", "progress": 40},
	"production_complete": {"label": "Production Complete", "css": "primary", "progress": 70},
	"partially_shipped": {"label": "Partially Shipped", "css": "primary", "progress": 85},
	"shipped": {"label": "Shipped", "css": "success", "progress": 95},
	"completed": {"label": "Completed", "css": "success", "progress": 100},
	"on_hold": {"label": "On Hold", "css": "secondary", "progress": 0},
	"cancelled": {"label": "Cancelled", "css": "danger", "progress": 0},
	"issue": {"label": "Issue", "css": "danger", "progress": 0},
}


def derive_order_portal_status(
	docstatus,
	erp_status,
	per_delivered=0,
	per_billed=0,
	work_orders=None,
	production_complete=None,
):
	"""Map authoritative ERP facts to one customer-facing status key.

	Args:
		docstatus: Sales Order docstatus (0 draft, 1 submitted, 2 cancelled).
		erp_status: Sales Order ``status``.
		per_delivered: Sales Order ``per_delivered`` (0-100).
		per_billed: Sales Order ``per_billed`` (0-100).
		work_orders: iterable of dicts with ``status``, ``qty`` and
			``produced_qty`` for Work Orders linked to this Sales Order.

	Production facts come from Work Order quantities, never from delivery.
	"""
	if docstatus == 2 or erp_status == "Cancelled":
		return "cancelled"
	if docstatus == 0:
		return "order_request"
	if erp_status == "On Hold":
		return "on_hold"

	per_delivered = float(per_delivered or 0)
	per_billed = float(per_billed or 0)

	if (per_delivered >= 100 and per_billed >= 100) or erp_status == "Completed":
		return "completed"
	if per_delivered >= 100:
		return "shipped"
	if per_delivered > 0:
		return "partially_shipped"

	work_orders = list(work_orders or [])
	if work_orders:
		total = sum(float(w.get("qty") or 0) for w in work_orders)
		produced = sum(float(w.get("produced_qty") or 0) for w in work_orders)
		all_done = all(w.get("status") == "Completed" for w in work_orders)
		if production_complete is True or (
			production_complete is None and total and (all_done or produced >= total)
		):
			return "production_complete"
		if produced > 0 or any(w.get("status") == "In Process" for w in work_orders):
			return "in_production"
		if any(w.get("status") in ("Not Started", "Draft", "Submitted") for w in work_orders):
			return "approved"

	return "approved"


def order_status_meta(key):
	return ORDER_PORTAL_STATUSES.get(key) or ORDER_PORTAL_STATUSES["approved"]


def order_status_label(key):
	return _(order_status_meta(key)["label"])


def order_status_class(key):
	return order_status_meta(key)["css"]


def order_status_progress(key):
	return order_status_meta(key)["progress"]
