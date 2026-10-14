# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Stable portal URLs for schedule lines (UI-1).

Lines are addressed by their line key, which survives reordering, instead of
their position in the schedule. The old ``/portal/edit_fixture?line_idx=``
links keep working by redirecting here.
"""

from urllib.parse import quote

import frappe


def line_key(line):
	return line.get("line_key") or line.get("name")


def edit_url(schedule_name, line):
	return f"/portal/schedules/{quote(str(schedule_name), safe='')}/lines/{quote(str(line_key(line)), safe='')}/edit"


def find_line(schedule, key):
	"""(index, line) for the line whose key (or row name) is ``key``, else (None, None)."""
	for index, line in enumerate(schedule.get("lines") or []):
		if key and key in (line.get("line_key"), line.get("name")):
			return index, line
	return None, None


def redirect(location):
	frappe.local.flags.redirect_location = location
	raise frappe.Redirect
