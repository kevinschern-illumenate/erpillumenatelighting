# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Orders Page Controller

View and track sales orders for the current user's customer.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.orders import search_orders
from illumenate_lighting.illumenate_lighting.portal.status import order_status_class

no_cache = 1


def get_context(context):
	"""Get context for the orders list portal page."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	# One read model for list, detail and dashboard: customer-scoped Sales
	# Orders with a portal status derived from Work Orders / deliveries.
	context.update(search_orders(search=frappe.form_dict.get("search"), status=frappe.form_dict.get("status") or "all", page=frappe.form_dict.get("page") or 1))
	context.order_status_class = order_status_class
	context.title = _("My Orders")
	context.no_cache = 1

	return context
