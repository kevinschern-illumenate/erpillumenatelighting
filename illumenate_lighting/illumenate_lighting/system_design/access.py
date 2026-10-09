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
	# Design staff review and support every dealer's designs, so they read the schedules behind them.
	if not can_read_schedule(doc) and not _is_design_staff():
		raise DesignError("NOT_FOUND", _("Schedule not found"))
	return doc


def require_edit(schedule, allow_locked=False):
	"""Return the schedule document when the session user may change it.

	A readable schedule the user may not edit is ``FORBIDDEN``; a locked schedule is ``LOCKED`` unless
	``allow_locked`` (for records that leave the schedule as it is, such as generated drawings).
	"""
	from illumenate_lighting.illumenate_lighting.portal.access import can_edit_schedule

	doc = require_read(schedule)
	if not can_edit_schedule(doc):
		raise DesignError("FORBIDDEN", _("You can view this schedule but not change it"))
	if doc.get("is_locked") and not allow_locked:
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


# --- ilL-System-Design records (WP-2.4) -----------------------------------------------------------

DESIGN_DOCTYPE = "ilL-System-Design"
DESIGN_STAFF_CAPABILITIES = ("design_review", "engineering")


def _is_design_staff(user=None):
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	return any(allowed(name, user) for name in DESIGN_STAFF_CAPABILITIES)


def design_permission(doc, ptype="read", user=None):
	"""``has_permission`` hook: a design follows its schedule; design staff keep their role rights."""
	from illumenate_lighting.illumenate_lighting.portal.access import READ_PTYPES, schedule_permission

	user = user or frappe.session.user
	if user == "Guest":
		return False
	if user == "Administrator" or _is_design_staff(user):
		return True
	if not doc.get("fixture_schedule") or not frappe.db.exists(SCHEDULE_DOCTYPE, doc.fixture_schedule):
		return False
	schedule = frappe.get_doc(SCHEDULE_DOCTYPE, doc.fixture_schedule)
	return schedule_permission(schedule, "read" if ptype in READ_PTYPES else "write", user)


def design_query_conditions(user=None):
	"""List filter matching :func:`design_permission` for reads."""
	from illumenate_lighting.illumenate_lighting.portal.access import (
		SCHEDULE_TABLE,
		schedule_query_conditions,
	)

	user = user or frappe.session.user
	if user == "Guest":
		return "1=0"
	if user == "Administrator" or _is_design_staff(user):
		return ""
	conditions = schedule_query_conditions(user)
	if not conditions:
		return ""
	return (
		f"`tab{DESIGN_DOCTYPE}`.fixture_schedule in "
		f"(select {SCHEDULE_TABLE}.name from {SCHEDULE_TABLE} where {conditions})"
	)


def require_design(name, schedule=None):
	"""Return a design the user may read; ``NOT_FOUND`` when absent, unreadable or on another schedule."""
	_require_login()
	if not name or not isinstance(name, str) or not frappe.db.exists(DESIGN_DOCTYPE, name):
		raise DesignError("NOT_FOUND", _("Design not found"))
	design = frappe.get_doc(DESIGN_DOCTYPE, name)
	if schedule and design.fixture_schedule != schedule:
		raise DesignError("NOT_FOUND", _("Design not found"))
	require_read(design.fixture_schedule)
	return design
