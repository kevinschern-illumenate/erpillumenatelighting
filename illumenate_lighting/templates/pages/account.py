# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Account Settings Page Controller

User profile, notifications, and account preferences.
"""

import frappe
from frappe import _

no_cache = 1


def get_context(context):
	"""Get context for the account settings portal page."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	# Get user details
	user = frappe.get_doc("User", frappe.session.user)
	context.user = {
		"email": user.email,
		"first_name": user.first_name,
		"last_name": user.last_name,
		"full_name": user.full_name,
		"phone": user.phone,
		"user_image": user.user_image,
		"job_title": getattr(user, "job_title", None),
	}

	# Get customer details if linked
	customer_name = _get_user_customer(frappe.session.user)
	if customer_name:
		customer = frappe.get_doc("Customer", customer_name)
		context.customer = {
			"name": customer.name,
			"customer_name": customer.customer_name,
			"customer_type": customer.customer_type,
			"territory": customer.territory,
			"customer_group": customer.customer_group,
			"default_currency": customer.default_currency,
		}
	else:
		context.customer = None

	context.title = _("Account Settings")
	context.no_cache = 1

	return context


def _get_user_customer(user):
	"""Get the customer linked to the user via Contact."""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
	)
	return _get_user_customer(user)
