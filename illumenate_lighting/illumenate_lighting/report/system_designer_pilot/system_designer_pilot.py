# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""System Designer pilot use by schedule (WP-3.9, plan §23), from ``system_design:*`` events.

One row per schedule: how often it was opened and saved, risers exported, checks fixed, the time
from first open to first riser, and the dealer's rating. No prices or costs.
"""

import json
from statistics import mean

import frappe
from frappe import _
from frappe.utils import get_datetime

EVENT = "ilL-Portal-Event"
SCHEDULE = "ilL-Project-Fixture-Schedule"


def execute(filters=None):
	from frappe.utils import add_days, getdate, nowdate

	filters = frappe._dict(filters or {})
	to_date = getdate(filters.get("to_date") or nowdate())
	from_date = getdate(filters.get("from_date") or add_days(to_date, -30))
	events = frappe.get_all(
		EVENT,
		filters={
			"event_key": ["like", "system_design:%"],
			"creation": ["between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59.999999"]],
		},
		fields=["event_key", "message", "subject", "creation"],
		order_by="creation asc",
	)
	schedules = {row.get("schedule") for row in map(_message, events)} - {None}
	customers = {}
	if schedules:
		customers = {
			row.name: row.customer
			for row in frappe.get_all(
				SCHEDULE, filters={"name": ["in", list(schedules)]}, fields=["name", "customer"]
			)
		}
	rows = pilot_rows(events, customers)
	if filters.get("customer"):
		rows = [row for row in rows if row["customer"] == filters.customer]
	return get_columns(), rows


def get_columns():
	return [
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 170,
		},
		{
			"label": _("Schedule"),
			"fieldname": "schedule",
			"fieldtype": "Link",
			"options": SCHEDULE,
			"width": 170,
		},
		{
			"label": _("Design"),
			"fieldname": "design",
			"fieldtype": "Link",
			"options": "ilL-System-Design",
			"width": 150,
		},
		{"label": _("Users"), "fieldname": "users", "fieldtype": "Int", "width": 70},
		{"label": _("Opened"), "fieldname": "opened", "fieldtype": "Int", "width": 80},
		{"label": _("Saved"), "fieldname": "saved", "fieldtype": "Int", "width": 70},
		{"label": _("Risers"), "fieldname": "riser_exported", "fieldtype": "Int", "width": 70},
		{"label": _("Checks fixed"), "fieldname": "check_fixed", "fieldtype": "Int", "width": 100},
		{
			"label": _("Minutes to first riser"),
			"fieldname": "minutes_to_riser",
			"fieldtype": "Float",
			"width": 150,
		},
		{"label": _("Rating"), "fieldname": "rating", "fieldtype": "Float", "width": 70},
		{"label": _("Comments"), "fieldname": "comments", "fieldtype": "Data", "width": 300},
		{"label": _("Last activity"), "fieldname": "last_activity", "fieldtype": "Datetime", "width": 160},
	]


def _message(event):
	try:
		value = json.loads(event.get("message") or "{}")
	except ValueError:
		return {}
	return value if isinstance(value, dict) else {}


def pilot_rows(events, customers):
	"""Aggregate ``system_design:*`` events (oldest first) into one row per schedule."""
	by_schedule = {}
	for event in events:
		message = _message(event)
		schedule = message.get("schedule")
		if not schedule:
			continue
		parts = str(event.get("event_key") or "").split(":")
		kind = message.get("event") or (parts[1] if len(parts) > 1 else None)
		row = by_schedule.setdefault(
			schedule,
			{
				"customer": customers.get(schedule),
				"schedule": schedule,
				"design": None,
				"users": set(),
				"opened": 0,
				"saved": 0,
				"riser_exported": 0,
				"check_fixed": 0,
				"first_opened": None,
				"first_riser": None,
				"ratings": [],
				"comments": [],
				"last_activity": None,
			},
		)
		at = get_datetime(event.get("creation"))
		row["last_activity"] = at
		row["design"] = message.get("design") or row["design"]
		if event.get("subject"):
			row["users"].add(event.get("subject"))
		if kind == "opened":
			row["opened"] += 1
			row["first_opened"] = row["first_opened"] or at
		elif kind == "saved":
			row["saved"] += 1
		elif kind == "riser_exported":
			row["riser_exported"] += 1
			row["first_riser"] = row["first_riser"] or at
		elif kind == "check_fixed":
			row["check_fixed"] += len(message.get("codes") or []) or 1
		elif kind == "feedback":
			if isinstance(message.get("rating"), int):
				row["ratings"].append(message["rating"])
			if message.get("comment"):
				row["comments"].append(str(message["comment"]))
	rows = []
	for row in by_schedule.values():
		start, riser = row.pop("first_opened"), row.pop("first_riser")
		ratings, comments = row.pop("ratings"), row.pop("comments")
		rows.append(
			{
				**row,
				"users": len(row["users"]),
				"minutes_to_riser": round((riser - start).total_seconds() / 60, 1)
				if start and riser and riser >= start
				else None,
				"rating": round(mean(ratings), 2) if ratings else None,
				"comments": " | ".join(comments)[:500],
			}
		)
	return sorted(rows, key=lambda row: row["last_activity"], reverse=True)
