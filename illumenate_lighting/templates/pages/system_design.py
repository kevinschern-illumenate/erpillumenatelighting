# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""ilLumenate System Designer entry point (``/portal/schedules/<schedule>/design`` and ``/portal/design``).

The React app is a committed bundle (``public/system_designer``) mounted with the schedule name, the
CSRF token and the endpoint base. Schedules the user cannot read look exactly like missing ones.
"""

from pathlib import Path
from urllib.parse import quote

import frappe
from frappe import _

no_cache = 1
ASSETS = "/assets/illumenate_lighting/system_designer/designer"
BUNDLE = Path(__file__).resolve().parents[2] / "public/system_designer/designer.js"
API_BASE = "/api/method/illumenate_lighting.illumenate_lighting.system_design.api"
SCHEDULE_DOCTYPE = "ilL-Project-Fixture-Schedule"


def _redirect(location):
	frappe.local.flags.redirect_location = location
	raise frappe.Redirect


def get_context(context):
	from illumenate_lighting.illumenate_lighting.portal.access import can_read_schedule
	from illumenate_lighting.illumenate_lighting.system_design.settings import is_enabled_for

	if frappe.session.user == "Guest":
		query = frappe.request.query_string
		if isinstance(query, bytes):
			query = query.decode()
		url = frappe.request.path + ("?" + query if query else "")
		_redirect("/login?redirect-to=" + quote(url, safe=""))

	schedule = frappe.form_dict.get("schedule") or None
	if schedule is not None:
		if (
			not isinstance(schedule, str)
			or not frappe.db.exists(SCHEDULE_DOCTYPE, schedule)
			or not can_read_schedule(frappe.get_doc(SCHEDULE_DOCTYPE, schedule))
		):
			frappe.throw(_("Schedule not found"), frappe.DoesNotExistError)

	if not is_enabled_for():
		_redirect(f"/portal/schedules/{quote(schedule, safe='')}" if schedule else "/portal/projects")

	version = int(BUNDLE.stat().st_mtime) if BUNDLE.exists() else 0
	context.update(
		{
			"title": "ilLumenate System Designer",
			"no_cache": 1,
			"assets": ASSETS,
			"asset_version": version,
			"schedule_name": schedule,
			"mount_options": {
				"schedule": schedule,
				"csrfToken": frappe.sessions.get_csrf_token(),
				"apiBase": API_BASE,
			},
		}
	)
	return context
