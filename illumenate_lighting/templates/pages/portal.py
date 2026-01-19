# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Landing Page Controller

Main dashboard page for portal users showing quick access to all features.
"""

import frappe
from frappe import _

no_cache = 1


def get_context(context):
	"""Get context for the portal landing page."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	# Get user info
	user_doc = frappe.get_doc("User", frappe.session.user)
	context.user_name = user_doc.first_name or user_doc.full_name or user_doc.name.split("@")[0]

	# Get user's customer
	context.customer_name = _get_user_customer_name(frappe.session.user)

	# Get statistics
	context.stats = _get_portal_stats()

	# Get recent projects
	context.recent_projects = frappe.get_all(
		"ilL-Project",
		fields=["name", "project_name", "customer", "status", "modified"],
		order_by="modified desc",
		limit=5,
	)

	# Get recent orders
	customer = _get_user_customer(frappe.session.user)
	if customer:
		context.recent_orders = frappe.get_all(
			"Sales Order",
			filters={"customer": customer, "docstatus": ["!=", 2]},
			fields=["name", "transaction_date", "status", "grand_total"],
			order_by="creation desc",
			limit=5,
		)
	else:
		context.recent_orders = []

	# Helper function for order status badge class
	context.order_status_class = _order_status_class

	context.title = _("Portal")
	context.no_cache = 1

	return context


def _get_user_customer(user):
	"""Get the customer linked to the user via Contact."""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
	)
	return _get_user_customer(user)


def _get_user_customer_name(user):
	"""Get the display name of the customer linked to the user."""
	customer = _get_user_customer(user)
	if customer:
		return frappe.db.get_value("Customer", customer, "customer_name") or customer
	return None


def _get_portal_stats():
	"""Get statistics for the portal dashboard."""
	stats = {
		"active_projects": 0,
		"total_schedules": 0,
		"pending_orders": 0,
		"ready_orders": 0,
		"pending_drawings": 0,
		"ready_drawings": 0,
	}

	# Count active projects
	stats["active_projects"] = frappe.db.count("ilL-Project", {"status": "ACTIVE"})

	# Count schedules
	stats["total_schedules"] = frappe.db.count("ilL-Project-Fixture-Schedule")

	# Count orders by status
	customer = _get_user_customer(frappe.session.user)
	if customer:
		stats["pending_orders"] = frappe.db.count(
			"Sales Order",
			{"customer": customer, "status": ["in", ["To Deliver and Bill", "To Deliver"]], "docstatus": 1}
		)
		stats["ready_orders"] = frappe.db.count(
			"Sales Order",
			{"customer": customer, "status": ["in", ["To Bill", "Completed"]], "docstatus": 1}
		)

	# Count drawing requests if the doctype exists
	if frappe.db.exists("DocType", "ilL-Document-Request"):
		stats["pending_drawings"] = frappe.db.count(
			"ilL-Document-Request",
			{"status": ["in", ["Submitted", "In Progress", "Waiting on Customer"]]}
		)
		stats["ready_drawings"] = frappe.db.count(
			"ilL-Document-Request",
			{"status": ["in", ["Completed", "Closed"]]}
		)

	return stats


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
