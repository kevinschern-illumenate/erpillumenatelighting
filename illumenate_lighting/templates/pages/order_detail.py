# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Order Detail Page Controller

Detailed view of a single sales order with tracking and items.
"""

import frappe
from frappe import _

no_cache = 1


def get_context(context):
	"""Get context for the order detail portal page."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	order_name = frappe.form_dict.get("order")

	if not order_name or not frappe.db.exists("Sales Order", order_name):
		context.order = None
		context.items = []
		context.deliveries = []
		context.title = _("Order Not Found")
		return context

	# Get order details via API
	from illumenate_lighting.illumenate_lighting.api.portal import get_order_details

	result = get_order_details(order_name)

	if not result.get("success"):
		context.order = None
		context.items = []
		context.deliveries = []
		context.title = _("Order Not Found")
		return context

	context.order = frappe._dict(result.get("order", {}))
	context.items = result.get("items", [])
	context.deliveries = result.get("deliveries", [])

	# Calculate progress
	context.progress_percent = _calculate_progress(context.order)
	context.production_started = _check_production_started(order_name)
	context.production_complete = context.order.per_delivered > 0
	context.production_date = _get_production_date(order_name) if context.production_started else None

	context.title = context.order.name
	context.no_cache = 1

	return context


def _calculate_progress(order):
	"""Calculate progress percentage for the timeline."""
	if order.status == "Completed":
		return 100
	elif order.per_delivered >= 100:
		return 85
	elif order.per_delivered > 0:
		return 70
	elif order.status in ["To Deliver", "To Deliver and Bill"]:
		return 50
	elif order.docstatus == 1:
		return 25
	return 0


def _check_production_started(sales_order):
	"""Check if production has started for a sales order."""
	work_orders = frappe.db.count(
		"Work Order",
		{"sales_order": sales_order, "docstatus": 1}
	)
	return work_orders > 0


def _get_production_date(sales_order):
	"""Get the date production started."""
	work_order = frappe.db.get_value(
		"Work Order",
		{"sales_order": sales_order, "docstatus": 1},
		"planned_start_date",
		order_by="creation asc"
	)
	return work_order
