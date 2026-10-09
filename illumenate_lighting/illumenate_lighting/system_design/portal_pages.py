# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""What the schedule and project portal pages show about system designs (WP-4.5, D2).

Both helpers return nothing for users the designer is not enabled for, and never raise: a failure is
logged and the page renders as it did before the designer existed.
"""

from urllib.parse import quote

import frappe
from frappe import _

DESIGN_DOCTYPE = "ilL-System-Design"
STATUS_TONES = {
	"Draft": "secondary",
	"In Review": "info",
	"Changes Requested": "warning",
	"Approved": "success",
	"Superseded": "dark",
}


def design_url(schedule):
	return f"/portal/schedules/{quote(schedule, safe='')}/design"


def review_chip(requirement, design_status=None):
	"""Pure: ``{label, tone}`` for the D4 state of a schedule, or ``None`` when no review is needed."""
	if not requirement or not requirement.get("required"):
		return None
	if requirement.get("satisfied"):
		if requirement.get("override"):
			return {"label": _("Review overridden"), "tone": "success"}
		return {"label": _("Review approved"), "tone": "success"}
	if design_status == "In Review":
		return {"label": _("In review"), "tone": "info"}
	return {"label": _("Review required"), "tone": "warning"}


def _design_row(record):
	return {
		"name": record.name,
		"revision": record.revision,
		"status": record.status,
		"tone": STATUS_TONES.get(record.status, "secondary"),
	}


def schedule_card(schedule_doc):
	"""``{url, design, review}`` for the schedule page, or ``None`` when the designer is off for the user."""
	from illumenate_lighting.illumenate_lighting.system_design import gate
	from illumenate_lighting.illumenate_lighting.system_design.designs import current_design
	from illumenate_lighting.illumenate_lighting.system_design.settings import is_enabled_for

	try:
		if not is_enabled_for():
			return None
		record = current_design(schedule_doc)
		requirement = gate.schedule_requirement(schedule_doc)
		return {
			"url": design_url(schedule_doc.name),
			"design": _design_row(record) if record else None,
			"review": review_chip(requirement, record.status if record else None),
		}
	except Exception:
		frappe.log_error(title=f"System Designer schedule card: {schedule_doc.name}"[:140])
		return None


def project_designs(schedules):
	"""Current designs of the given (already readable) schedules, newest first, for the project page.

	``None`` when the designer is off for the user, so the page leaves out the Designs tab.
	"""
	from illumenate_lighting.illumenate_lighting.system_design.settings import is_enabled_for

	try:
		if not is_enabled_for() or not frappe.db.exists("DocType", DESIGN_DOCTYPE):
			return None
		by_name = {row.name: row for row in schedules}
		if not by_name:
			return []
		rows = frappe.get_all(
			DESIGN_DOCTYPE,
			filters={"fixture_schedule": ["in", sorted(by_name)], "is_current": 1},
			fields=[
				"name",
				"title",
				"fixture_schedule",
				"schedule_version",
				"revision",
				"status",
				"modified",
			],
			order_by="modified desc",
		)
		designs = []
		for row in rows:
			schedule = by_name[row.fixture_schedule]
			if (row.schedule_version or 0) != (schedule.get("version") or 0):
				continue
			designs.append(
				{
					**_design_row(row),
					"title": row.title,
					"schedule": row.fixture_schedule,
					"schedule_name": schedule.get("schedule_name") or row.fixture_schedule,
					"url": design_url(row.fixture_schedule),
					"modified": row.modified,
				}
			)
		return designs
	except Exception:
		frappe.log_error(title="System Designer project designs"[:140])
		return None
