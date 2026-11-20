"""Scheduled jobs for Kevin's Desk (hooks.scheduler_events)."""

import frappe

from illumenate_lighting.kevins_desk import access


def warm():
	"""Every 10 minutes on weekday working hours: rebuild the desk's caches as the desk owner,
	so the page loads from cache (and Gmail labels stay current) without waiting on Gmail or ERPNext."""
	conf = access.config()
	owner = conf.get("desk_owner")
	if not (conf.get("enabled") and owner and access.is_owner(conf, owner)):
		return
	from illumenate_lighting.kevins_desk import api, pipeline

	previous = frappe.session.user
	frappe.set_user(owner)
	try:
		api.build_today(owner, refresh=True)
		api.cached("signals", pipeline.signals, refresh=True)
	except Exception:
		frappe.log_error(title="Kevin's Desk: warm failed")
	finally:
		frappe.set_user(previous)
