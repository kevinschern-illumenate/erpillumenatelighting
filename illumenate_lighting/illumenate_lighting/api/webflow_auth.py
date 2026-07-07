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


@frappe.whitelist(allow_guest=True)
def get_user_context() -> dict:
	"""Return auth and dealer state for the Webflow configurator widget."""
	origin = frappe.request.headers.get("Origin", "") if frappe.request else ""
	allowed_origins = {
		"https://illumenate.lighting",
		"https://www.illumenate.lighting",
	}
	if origin in allowed_origins or origin.endswith(".webflow.io") or origin.endswith(".vercel.app"):
		frappe.local.response["Access-Control-Allow-Origin"] = origin
		frappe.local.response["Access-Control-Allow-Credentials"] = "true"
		frappe.local.response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
		frappe.local.response["Access-Control-Allow-Headers"] = "X-Requested-With, Content-Type"

	user = frappe.session.user
	is_logged_in = user != "Guest"
	is_dealer = False
	is_internal = False
	customer = None
	customer_name = None

	if is_logged_in:
		from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
			_get_user_customer,
			_is_dealer_user,
			_is_internal_user,
		)

		roles = set(frappe.get_roles(user))
		is_dealer = _is_dealer_user(user) or bool(roles & {"Dealer", "System Manager", "Administrator"})
		is_internal = _is_internal_user(user)
		customer = _get_user_customer(user)
		if customer:
			customer_name = frappe.db.get_value("Customer", customer, "customer_name")

	# SECURITY: API key/secret are intentionally NOT returned here. This endpoint
	# is guest-whitelisted and reflects CORS credentials to preview/app subdomains
	# (*.webflow.io, *.vercel.app); returning secrets would let any such origin
	# read a logged-in user's API secret. The widget authenticates subsequent
	# calls via the session cookie (credentials: 'include') instead.
	return {
		"success": is_logged_in,
		"is_logged_in": is_logged_in,
		"user": user if is_logged_in else None,
		"full_name": frappe.utils.get_fullname(user) if is_logged_in else None,
		"is_dealer": is_dealer,
		"is_internal": is_internal,
		"customer": customer,
		"customer_name": customer_name,
	}
