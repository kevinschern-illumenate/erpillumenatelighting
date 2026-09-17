# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Order Detail Page Controller

Detailed view of a single sales order with tracking and items.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.orders import get_order_read_model

no_cache = 1


def get_context(context):
	"""Get context for the order detail portal page."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	order_name = frappe.form_dict.get("order")
	model = get_order_read_model(order_name, frappe.session.user) if order_name else None

	if model is None:
		context.order = None
		context.items = []
		context.deliveries = []
		context.title = _("Order Not Found")
		return context

	context.order = model["order"]
	context.items = model["lines"]
	context.deliveries = model["shipments"]
	context.invoices = model["invoices"]
	context.production = model["production"]
	context.schedule = model["schedule"]
	context.timeline = model["timeline"]
	context.actions = model["actions"]

	# Derived from Work Order quantities and Delivery Notes, not guessed
	context.progress_percent = context.order.progress_percent
	context.production_started = context.order.production_started
	context.production_complete = context.order.production_complete
	context.production_date = (context.order.production or {}).get("started_on")
	context.download_url = (
		"/api/method/illumenate_lighting.illumenate_lighting.api.portal.download_order_document"
	)

	context.title = context.order.name
	context.no_cache = 1

	return context
