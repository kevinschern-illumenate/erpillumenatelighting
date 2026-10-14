# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Address schedule lines by their stable ``line_key`` and refuse stale edits.

A positional index is only meaningful for the exact revision the browser loaded:
another tab, user or a Desk edit can insert, delete or reorder lines in between,
and the click then lands on a different line. Callers send the line's key and
the ``modified`` timestamp they loaded; a positional index is still accepted from
older pages.
"""

import frappe
from frappe import _

STALE_MESSAGE = "This schedule changed since you opened it. Reload to see the latest version."


def require_fresh(schedule, expected_modified=None) -> None:
	if expected_modified and str(expected_modified) != str(schedule.modified):
		frappe.throw(_(STALE_MESSAGE))


def line_index(schedule, line_key=None, line_idx=None) -> int:
	"""Position of the addressed line in ``schedule.lines``; throws a user-facing error.

	Matches ``portal.configuration.resolve_line``: a key may be the line's
	``line_key`` or its row name.
	"""
	lines = schedule.lines or []
	if line_key:
		matches = [
			index
			for index, line in enumerate(lines)
			if line.get("line_key") == line_key or line.get("name") == line_key
		]
		if len(matches) != 1:
			frappe.throw(_("The selected line changed or is unavailable; reload the schedule"))
		return matches[0]
	try:
		index = int(line_idx)
	except (TypeError, ValueError):
		frappe.throw(_("Choose a schedule line"))
	if index < 0 or index >= len(lines):
		frappe.throw(_("The selected line is unavailable"))
	return index
