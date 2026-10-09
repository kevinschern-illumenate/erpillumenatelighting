# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Typed access to ``ilL-System-Designer-Settings``.

A Single that has never been saved stores nothing, so every value falls back to the plan's defaults
(H4.1). Callers always get a complete, correctly typed set.
"""

import frappe

DOCTYPE = "ilL-System-Designer-Settings"
PILOT_DOCTYPE = "ilL-Child-Designer-Pilot-Customer"

DEFAULTS = {
	"enabled": 0,
	"vd_target_class2_pct": 3.0,
	"vd_target_line_pct": 3.0,
	"vd_target_landscape_pct": 5.0,
	"nec_edition": "2023",
	"wire_waste_pct": 10.0,
	"max_watts_per_run_fallback": 85.0,
	"review_gate_enabled": 0,
	"review_gate_watts": 1500.0,
	"review_gate_dmx": 1,
	"review_gate_phase_dimming": 1,
	"share_default_days": 90,
	"share_max_days": 90,
	"group_threshold_qty": 6,
	"default_distance_same_space_ft": 10.0,
	"default_distance_adjacent_ft": 25.0,
	"default_distance_other_level_ft": 40.0,
	"plan_route_slack_pct": 15.0,
	"terms_text": (
		"Design aid. Verify against product documentation and local code. "
		"Line-voltage work by a licensed electrician."
	),
	"reviewer_assignment": "Round Robin",
}


class Settings(dict):
	"""Settings values with attribute access (``settings().vd_target_class2_pct``)."""

	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(key) from None


def _coerce(default, value):
	if value is None or value == "":
		return default
	try:
		if isinstance(default, float):
			return float(value)
		if isinstance(default, int):
			return int(float(value))
	except (TypeError, ValueError):
		return default
	return str(value)


def settings() -> Settings:
	stored = frappe.db.get_singles_dict(DOCTYPE) or {}
	values = Settings({key: _coerce(default, stored.get(key)) for key, default in DEFAULTS.items()})
	values["pilot_customers"] = pilot_customers()
	return values


def pilot_customers() -> list:
	rows = frappe.get_all(
		PILOT_DOCTYPE,
		filters={"parent": DOCTYPE, "parenttype": DOCTYPE, "parentfield": "pilot_customers"},
		pluck="customer",
	)
	return sorted({row for row in rows or [] if row})


def is_staff(user=None) -> bool:
	"""Staff who may use and review the designer regardless of the rollout switch."""
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	return allowed("engineering", user) or allowed("design_review", user)


def is_enabled_for(user=None) -> bool:
	"""Whether the designer is available to ``user`` at all (schedule access is checked separately).

	On for staff, for everyone once ``enabled`` is set, and for users of a pilot customer before that.
	"""
	user = user or frappe.session.user
	if user == "Guest":
		return False
	if is_staff(user):
		return True
	values = settings()
	if values.enabled:
		return True
	if not values.pilot_customers:
		return False
	from illumenate_lighting.illumenate_lighting.portal.access import get_actor

	actor = get_actor(user)
	return bool(not actor.is_guest and actor.customer and actor.customer in values.pilot_customers)
