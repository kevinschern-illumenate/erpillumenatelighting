# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Support Page Controller

Help center, FAQ, and support ticket submission.
"""

import frappe
from frappe import _

no_cache = 1


def get_context(context):
	"""Get context for the support portal page."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	from illumenate_lighting.illumenate_lighting.portal.access import get_actor
	from illumenate_lighting.illumenate_lighting.portal.support import list_tickets

	actor = get_actor()
	customer = actor.customer if actor.is_dealer else None

	# Get recent orders for the support form
	if customer:
		context.recent_orders = frappe.get_all(
			"Sales Order",
			filters={"customer": customer, "docstatus": 1},
			fields=["name", "transaction_date"],
			order_by="creation desc",
			limit=20,
		)
	else:
		context.recent_orders = []

	context.ticket_page = list_tickets(page=frappe.form_dict.get("page", 1), status=frappe.form_dict.get("status"))
	context.tickets = context.ticket_page["tickets"]

	context.title = _("Support")
	context.no_cache = 1

	return context


def _get_user_customer(user):
	"""Get the customer linked to the user via Contact."""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
	)
	return _get_user_customer(user)
