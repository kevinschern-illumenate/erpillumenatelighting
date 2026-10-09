# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Open, save, revise and copy ilL-System-Design records (WP-2.3, WP-2.4).

The document contract (validation and build hash) lives in :mod:`.design_schema` (WP-2.2).
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.system_design import access, catalog, expansion, gate
from illumenate_lighting.illumenate_lighting.system_design.design_schema import (
	build_hash,
	canonical_json,
	validate_design_json,
)
from illumenate_lighting.illumenate_lighting.system_design.errors import DesignError
from illumenate_lighting.illumenate_lighting.system_design.settings import is_enabled_for, settings

__all__ = ["build_hash", "canonical_json", "find_schedules", "open_design", "validate_design_json"]

DESIGN_DOCTYPE = "ilL-System-Design"
FIND_LIMIT = 20
CLIENT_SETTINGS = (
	"vd_target_class2_pct",
	"vd_target_line_pct",
	"vd_target_landscape_pct",
	"wire_waste_pct",
	"max_watts_per_run_fallback",
	"group_threshold_qty",
	"default_distance_same_space_ft",
	"default_distance_adjacent_ft",
	"default_distance_other_level_ft",
	"plan_route_slack_pct",
	"nec_edition",
	"terms_text",
)


def require_designer():
	if not is_enabled_for():
		raise DesignError("FORBIDDEN", _("The System Designer is not available for your account yet"))


def _designs_exist():
	return bool(frappe.db.exists("DocType", DESIGN_DOCTYPE))


def permissions(doc):
	from illumenate_lighting.illumenate_lighting.portal.access import can_edit_schedule
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	return {
		"can_edit": bool(can_edit_schedule(doc) and not doc.get("is_locked")),
		"can_review": bool(allowed("design_review")),
		"can_view_pricing": "Can View Pricing" in frappe.get_roles(),
	}


def open_design(schedule, design=None):
	"""Everything the designer needs to start on a schedule (H6 ``open_design``)."""
	doc = access.require_read(schedule)
	require_designer()
	values = settings()
	snapshot_hash = catalog.current_snapshot_hash()
	payload = catalog.get_snapshot(snapshot_hash) or {"items": []}
	kinds = {item["id"]: item["specs"]["kind"] for item in payload["items"]}
	lines, builds, readiness = expansion.expand_schedule(doc, kinds)
	if design:
		# Saved designs arrive with ilL-System-Design (WP-2.4); until then no name can match.
		raise DesignError("NOT_FOUND", _("Design not found"))
	return {
		"schedule": {
			"name": doc.name,
			"schedule_name": doc.get("schedule_name"),
			"version": doc.get("version") or 0,
			"is_locked": bool(doc.get("is_locked")),
			"status": doc.get("status"),
			"project": doc.get("ill_project"),
		},
		"lines": lines,
		"builds": builds,
		"design": None,
		"design_meta": None,
		"catalog_hash": snapshot_hash,
		"readiness": readiness,
		"review_requirement": gate.review_requirement(lines, builds, values),
		"permissions": permissions(doc),
		"settings": {key: values[key] for key in CLIENT_SETTINGS},
	}


def find_schedules(query, limit=FIND_LIMIT):
	"""Schedules the user can read whose name, title or project matches ``query`` (≥ 2 characters)."""
	from illumenate_lighting.illumenate_lighting.portal.access import schedule_query_conditions

	if frappe.session.user == "Guest":
		raise DesignError("FORBIDDEN", _("Please log in to continue"))
	require_designer()
	text = str(query or "").strip()
	if len(text) < 2:
		raise DesignError("INVALID", _("Type at least two characters"))
	try:
		limit = max(1, min(int(limit or FIND_LIMIT), FIND_LIMIT))
	except (TypeError, ValueError):
		limit = FIND_LIMIT
	conditions = schedule_query_conditions()
	pattern = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
	table = "`tabilL-Project-Fixture-Schedule`"
	# ``conditions`` names the schedule table in full, so the query does not alias it.
	rows = frappe.db.sql(
		f"""
		select {table}.name, {table}.schedule_name, {table}.ill_project as project,
			proj.project_name, {table}.version
		from {table}
		left join `tabilL-Project` proj on proj.name = {table}.ill_project
		where ({table}.name like %(pattern)s or {table}.schedule_name like %(pattern)s
			or proj.project_name like %(pattern)s)
			{"and (" + conditions + ")" if conditions else ""}
		order by {table}.modified desc
		limit {limit}
		""",
		{"pattern": pattern},
		as_dict=True,
	)
	designed = set()
	if rows and _designs_exist():
		designed = set(
			frappe.get_all(
				DESIGN_DOCTYPE, filters={"schedule": ["in", [r["name"] for r in rows]]}, pluck="schedule"
			)
		)
	return [
		{
			"name": row["name"],
			"schedule_name": row.get("schedule_name"),
			"project": row.get("project"),
			"project_name": row.get("project_name"),
			"version": row.get("version") or 0,
			"has_design": row["name"] in designed,
		}
		for row in rows
	]
