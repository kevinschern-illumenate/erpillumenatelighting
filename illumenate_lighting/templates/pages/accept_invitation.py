"""Invitation tokens stay in the browser fragment until an authenticated POST."""

import frappe

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.signed_in_as = None if frappe.session.user == "Guest" else frappe.session.user
	context.signup_enabled = not frappe.db.get_single_value("Website Settings", "disable_signup")
