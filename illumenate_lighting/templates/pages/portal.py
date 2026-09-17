# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Landing Page Controller

Main dashboard page for portal users showing quick access to all features.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.access import (
	can_view_catalog,
	get_actor,
	project_query_conditions,
	schedule_query_conditions,
)
from illumenate_lighting.illumenate_lighting.portal.orders import list_orders
from illumenate_lighting.illumenate_lighting.portal.status import order_status_class

no_cache = 1


def get_context(context):
	"""Get context for the portal landing page."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	# Get user info
	user_doc = frappe.get_doc("User", frappe.session.user)
	context.user_name = user_doc.first_name or user_doc.full_name or user_doc.name.split("@")[0]

	actor = get_actor(frappe.session.user)
	context.customer_name = _get_user_customer_name(frappe.session.user)

	# Same read model as /portal/orders so counts, labels and recents agree.
	orders = list_orders(actor.user)
	context.stats = _get_portal_stats(actor, orders)

	# Get recent projects (respects permission_query_conditions)
	context.recent_projects = frappe.get_list(
		"ilL-Project",
		fields=["name", "project_name", "customer", "status", "modified"],
		order_by="modified desc",
		limit=5,
	)

	# Order requests are shown too, so a successful conversion is visible here.
	context.recent_orders = orders[:5]
	context.order_status_class = order_status_class
	context.can_view_catalog = can_view_catalog(actor.user)

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


def _scoped_count(doctype, conditions, extra_where="", params=None):
	"""Count rows the actor may read, using the same predicate as the lists."""
	where = [c for c in (conditions, extra_where) if c]
	sql = f"SELECT COUNT(*) FROM `tab{doctype}`"
	if where:
		sql += " WHERE " + " AND ".join(where)
	return frappe.db.sql(sql, params or {})[0][0]


def _get_portal_stats(actor, orders):
	"""Dashboard counts derived from the actor's visibility, not from a raw Customer filter."""
	stats = {
		"active_projects": 0,
		"total_schedules": 0,
		"order_requests": 0,
		"pending_orders": 0,
		"ready_orders": 0,
		"pending_drawings": 0,
		"ready_drawings": 0,
	}

	stats["active_projects"] = _scoped_count(
		"ilL-Project", project_query_conditions(actor.user), "`tabilL-Project`.status = 'ACTIVE'"
	)
	stats["total_schedules"] = _scoped_count(
		"ilL-Project-Fixture-Schedule", schedule_query_conditions(actor.user)
	)

	for order in orders:
		key = order.get("portal_status")
		if key == "order_request":
			stats["order_requests"] += 1
		elif key in ("approved", "in_production", "production_complete", "on_hold"):
			stats["pending_orders"] += 1
		elif key in ("partially_shipped", "shipped"):
			stats["ready_orders"] += 1

	from illumenate_lighting.illumenate_lighting.api.document_requests import (
		_scoped_request_count,
	)

	stats["pending_drawings"] = _scoped_request_count("pending", actor.user)
	stats["ready_drawings"] = _scoped_request_count("completed", actor.user)

	return stats
