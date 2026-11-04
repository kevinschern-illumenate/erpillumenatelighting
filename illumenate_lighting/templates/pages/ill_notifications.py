# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Portal notification list (hardening plan 8.5); opening it clears the nav badge."""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal import notification_center
from illumenate_lighting.illumenate_lighting.portal.web_guard import require_login

no_cache = 1


def get_context(context):
	require_login()
	if not notification_center.enabled():
		frappe.local.flags.redirect_location = "/portal"
		raise frappe.Redirect
	notifications = notification_center.recent()
	for entry in notifications:
		entry["when_label"] = frappe.utils.pretty_date(entry["when"])
	notification_center.mark_seen()
	context.notifications = notifications
	context.title = _("Notifications")
	context.no_cache = 1
	return context
