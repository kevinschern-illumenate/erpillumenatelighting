# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Orders Page Controller

View and track sales orders for the current user's customer.
"""

import frappe
from frappe import _

no_cache = 1


def get_context(context):
	"""Get context for the orders list portal page."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	# Get user's customer
	customer = _get_user_customer(frappe.session.user)

	if customer:
		# Get all orders for this customer
		orders = frappe.get_all(
			"Sales Order",
			filters={
				"customer": customer,
				"docstatus": ["!=", 2],  # Exclude cancelled
			},
			fields=[
				"name",
				"transaction_date",
				"delivery_date",
				"status",
				"grand_total",
				"currency",
				"total_qty",
				"po_no",
				"per_delivered",
				"per_billed",
				"docstatus",
			],
			order_by="creation desc",
		)

		# Add production status info
		for order in orders:
			order["production_started"] = _check_production_started(order.name)

		context.orders = orders
	else:
		context.orders = []

	context.order_status_class = _order_status_class
	context.title = _("My Orders")
	context.no_cache = 1

	return context


def _get_user_customer(user):
	"""Get the customer linked to the user via Contact."""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
	)
	return _get_user_customer(user)


def _check_production_started(sales_order):
	"""Check if production has started for a sales order."""
	# Check if there are any Work Orders linked to this Sales Order
	work_orders = frappe.db.count(
		"Work Order",
		{"sales_order": sales_order, "docstatus": 1}
	)
	return work_orders > 0


def _order_status_class(status):
	"""Get Bootstrap badge class for order status."""
	status_map = {
		"Draft": "secondary",
		"On Hold": "warning",
		"To Deliver and Bill": "info",
		"To Bill": "primary",
		"To Deliver": "info",
		"Completed": "success",
		"Cancelled": "danger",
		"Closed": "dark",
	}
	return status_map.get(status, "secondary")
