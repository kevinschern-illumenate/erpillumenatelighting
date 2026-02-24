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

	# Get job_title from the linked Contact (stored as designation)
	job_title = _get_contact_job_title(frappe.session.user)

	context.user_profile = {
		"email": user.email,
		"first_name": user.first_name,
		"last_name": user.last_name,
		"full_name": user.full_name,
		"phone": user.phone,
		"user_image": user.user_image,
		"job_title": job_title,
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

	# Load portal user settings (notification prefs, display prefs)
	context.portal_settings = _get_portal_settings(frappe.session.user)

	context.title = _("Account Settings")
	context.no_cache = 1

	return context


def _get_user_customer(user):
	"""Get the customer linked to the user via Contact."""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
	)
	return _get_user_customer(user)


def _get_contact_job_title(user):
	"""Get the job title (designation) from the Contact linked to this user."""
	contacts = frappe.get_all(
		"Contact",
		filters={"user": user},
		fields=["designation"],
		limit=1,
	)
	if contacts:
		return contacts[0].get("designation") or ""
	return ""


def _get_portal_settings(user):
	"""Load portal user settings from the ilL-Portal-User-Settings DocType."""
	settings_name = frappe.db.get_value(
		"ilL-Portal-User-Settings", {"user": user}, "name"
	)

	if settings_name:
		doc = frappe.get_doc("ilL-Portal-User-Settings", settings_name)
		return {
			"notify_orders": bool(doc.notify_orders),
			"notify_quotes": bool(doc.notify_quotes),
			"notify_drawings": bool(doc.notify_drawings),
			"notify_shipping": bool(doc.notify_shipping),
			"notify_marketing": bool(doc.notify_marketing),
			"language": doc.language or "en",
			"units": doc.units or "imperial",
			"date_format": doc.date_format or "mm/dd/yyyy",
			"timezone": doc.timezone or "America/New_York",
		}

	# Defaults if no record exists yet
	return {
		"notify_orders": True,
		"notify_quotes": True,
		"notify_drawings": True,
		"notify_shipping": True,
		"notify_marketing": False,
		"language": "en",
		"units": "imperial",
		"date_format": "mm/dd/yyyy",
		"timezone": "America/New_York",
	}
