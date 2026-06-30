# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect
	context.title = "Dealer Access Required"
	context.no_cache = 1
