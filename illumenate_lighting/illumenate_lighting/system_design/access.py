# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Design-level access checks on top of ``portal/access.py`` and ``portal/staff.py``.

Every System Designer endpoint starts with one of these (plan H1 rule 7). A schedule the user cannot
read raises ``NOT_FOUND``, exactly like a schedule that does not exist, so guessed names reveal nothing.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.system_design.errors import DesignError

SCHEDULE_DOCTYPE = "ilL-Project-Fixture-Schedule"


def _load_schedule(schedule):
	if not schedule or not isinstance(schedule, str) or not frappe.db.exists(SCHEDULE_DOCTYPE, schedule):
		raise DesignError("NOT_FOUND", _("Schedule not found"))
	return frappe.get_doc(SCHEDULE_DOCTYPE, schedule)


def _require_login():
	if frappe.session.user == "Guest":
		raise DesignError("FORBIDDEN", _("Please log in to continue"))


def require_read(schedule):
	"""Return the schedule document when the session user may read it."""
	from illumenate_lighting.illumenate_lighting.portal.access import can_read_schedule

	_require_login()
	doc = _load_schedule(schedule)
	if not can_read_schedule(doc):
		raise DesignError("NOT_FOUND", _("Schedule not found"))
	return doc


def require_edit(schedule):
	"""Return the schedule document when the session user may change it.

	A readable schedule the user may not edit is ``FORBIDDEN``; a locked schedule is ``LOCKED``.
	"""
	from illumenate_lighting.illumenate_lighting.portal.access import can_edit_schedule

	doc = require_read(schedule)
	if not can_edit_schedule(doc):
		raise DesignError("FORBIDDEN", _("You can view this schedule but not change it"))
	if doc.get("is_locked"):
		raise DesignError("LOCKED", _("This schedule version is locked"))
	return doc


def require_capability(name):
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	_require_login()
	if not allowed(name):
		raise DesignError("FORBIDDEN", _("This action requires an authorized staff account"))


def require_reviewer():
	"""Applications Engineers (D3) and System Managers."""
	require_capability("design_review")
