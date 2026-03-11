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

	# Get user's customer for order lookup
	customer = _get_user_customer(frappe.session.user)

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

	# Get existing support tickets if Issue doctype exists
	context.tickets = []
	if frappe.db.table_exists("Issue"):
		context.tickets = frappe.get_all(
			"Issue",
			filters={"raised_by": frappe.session.user},
			fields=["name", "subject", "status", "creation"],
			order_by="creation desc",
			limit=5,
		)

	context.title = _("Support")
	context.no_cache = 1

	return context


def _get_user_customer(user):
	"""Get the customer linked to the user via Contact."""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
	)
	return _get_user_customer(user)
