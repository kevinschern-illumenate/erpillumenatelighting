# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Webflow Authentication API

Provides authentication endpoints for the Webflow marketing site to
authenticate users against ERPNext and retrieve user context (role,
linked customer, API credentials).

Users log in on Webflow via a custom login form that authenticates against
ERPNext's /api/method/login. On success, this module provides endpoints
to retrieve the authenticated user's context for subsequent API calls.
"""

import frappe
from frappe import _


@frappe.whitelist(allow_guest=False)
def get_user_context() -> dict:
	"""
	Return the authenticated user's context for Webflow integration.

	Returns the user's linked Customer (via Contact → Dynamic Link → Customer),
	whether they have the "Dealer" role, and their API key/secret pair.

	This endpoint is called after successful login to populate the Webflow
	client-side session with user context.

	Returns:
		dict: {
			"success": True/False,
			"user": str (email),
			"full_name": str,
			"is_dealer": bool,
			"is_internal": bool,
			"customer": str or None,
			"customer_name": str or None,
			"api_key": str or None,
			"api_secret": str or None,
		}
	"""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
		_is_dealer_user,
		_is_internal_user,
	)

	user = frappe.session.user

	if user == "Guest":
		return {"success": False, "error": _("Authentication required")}

	is_dealer = _is_dealer_user(user)
	is_internal = _is_internal_user(user)
	customer = _get_user_customer(user)

	# Get customer display name
	customer_name = None
	if customer:
		customer_name = frappe.db.get_value("Customer", customer, "customer_name")

	# Get or generate API key/secret for the user
	api_key, api_secret = _get_or_generate_api_credentials(user)

	return {
		"success": True,
		"user": user,
		"full_name": frappe.utils.get_fullname(user),
		"is_dealer": is_dealer,
		"is_internal": is_internal,
		"customer": customer,
		"customer_name": customer_name,
		"api_key": api_key,
		"api_secret": api_secret,
	}


def _get_or_generate_api_credentials(user: str) -> tuple:
	"""
	Get existing API key/secret for a user, or generate new ones.

	Args:
		user: The user email/name

	Returns:
		tuple: (api_key, api_secret) or (None, None) if generation fails
	"""
	user_doc = frappe.get_doc("User", user)

	api_key = user_doc.api_key
	api_secret = None

	if not api_key:
		api_key = frappe.generate_hash(length=15)
		user_doc.api_key = api_key
		user_doc.save(ignore_permissions=True)

	api_secret = frappe.utils.password.get_decrypted_password(
		"User", user, fieldname="api_secret"
	)

	if not api_secret:
		api_secret = frappe.generate_hash(length=15)
		user_doc.api_secret = api_secret
		user_doc.save(ignore_permissions=True)

	return api_key, api_secret
