# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Landing Page Controller

The overview: what needs the user's attention first, then recent activity and quick actions.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal import action_center
from illumenate_lighting.illumenate_lighting.portal.access import can_view_catalog, get_actor
from illumenate_lighting.illumenate_lighting.portal.orders import list_orders
from illumenate_lighting.illumenate_lighting.portal.status import order_status_class
from illumenate_lighting.illumenate_lighting.portal.web_guard import require_login

no_cache = 1


def get_context(context):
	"""Get context for the portal landing page."""
	require_login()

	# Get user info
	user_doc = frappe.get_doc("User", frappe.session.user)
	context.user_name = user_doc.first_name or user_doc.full_name or user_doc.name.split("@")[0]

	actor = get_actor(frappe.session.user)
	context.customer_name = _get_user_customer_name(frappe.session.user)
	context.greeting = action_center.greeting()

	# Same read model as /portal/orders so labels and recents agree.
	orders = list_orders(actor.user)
	context.action_items = action_center.for_user(actor.user, orders)

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

	from illumenate_lighting.illumenate_lighting.portal.product_finder.presentation import banner

	context.finder_banner = banner()
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
