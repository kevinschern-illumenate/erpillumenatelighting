# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Draw-to-quote funnel by front end and week (implementation plan WP 1.5).

Counts, per drawing tool (AutoCAD, DXF, Bluebeam) and ISO week: previews, previews refused before
planning (an unreadable or invalid file), commits, and quote requests made from a schedule whose newest
import came from that tool. Previews and commits come from the ``ilL-Portal-Event`` rows the import
writes through ``system_design.telemetry`` (``preference = system_design``); quote requests from
``ilL-Quote-Request.cad_import``. A refused preview has no tool yet, so it is counted as ``unknown``.
"""

import json

import frappe
from frappe import _

EVENT = "ilL-Portal-Event"
IMPORT = "ilL-CAD-Import"
REQUEST = "ilL-Quote-Request"
STAGES = ("cad_preview", "cad_preview_failed", "cad_import")


def week_of(value):
	"""``2026-W47`` for a date or datetime (or its string form)."""
	from frappe.utils import getdate

	year, week, _day = getdate(value).isocalendar()
	return f"{year}-W{week:02d}"


def event_stage(row):
	"""``(stage, tool)`` of a telemetry row, or None when it is not a drawing-import event."""
	try:
		message = json.loads(row.get("message") or "{}")
	except ValueError:
		return None
	stage = message.get("event")
	if stage not in STAGES:
		return None
	return stage, message.get("source_tool") or "unknown"


def tally(events, requests):
	"""Rows ``{week, tool, previews, failed, imports, quote_requests}`` from events and quote requests."""
	rows = {}

	def row(week, tool):
		return rows.setdefault(
			(week, tool),
			{"week": week, "tool": tool, "previews": 0, "failed": 0, "imports": 0, "quote_requests": 0},
		)

	columns = {"cad_preview": "previews", "cad_preview_failed": "failed", "cad_import": "imports"}
	for event in events:
		found = event_stage(event)
		if found:
			stage, tool = found
			row(week_of(event["creation"]), tool)[columns[stage]] += 1
	for request in requests:
		row(week_of(request["creation"]), request.get("tool") or "unknown")["quote_requests"] += 1
	return sorted(rows.values(), key=lambda item: (item["week"], item["tool"]), reverse=True)


def execute(filters=None):
	from frappe.utils import add_days, getdate, nowdate

	filters = frappe._dict(filters or {})
	to_date = getdate(filters.get("to_date") or nowdate())
	from_date = getdate(filters.get("from_date") or add_days(to_date, -90))
	window = ["between", [str(from_date), f"{to_date} 23:59:59"]]
	events = frappe.get_all(
		EVENT,
		filters={
			"preference": "system_design",
			"event_key": ["like", "system_design:cad_%"],
			"creation": window,
		},
		fields=["creation", "message"],
	)
	requests = []
	if frappe.db.exists("DocType", IMPORT) and frappe.get_meta(REQUEST).has_field("cad_import"):
		requests = frappe.get_all(
			REQUEST,
			filters={"cad_import": ["is", "set"], "creation": window},
			fields=["creation", "cad_import"],
		)
		tools = (
			dict(
				frappe.get_all(
					IMPORT,
					filters={"name": ["in", sorted({row.cad_import for row in requests})]},
					fields=["name", "source_tool"],
					as_list=True,
				)
			)
			if requests
			else {}
		)
		requests = [{"creation": row.creation, "tool": tools.get(row.cad_import)} for row in requests]
	return get_columns(), tally(events, requests)


def get_columns():
	return [
		{"label": _("Week"), "fieldname": "week", "fieldtype": "Data", "width": 100},
		{"label": _("Drawing tool"), "fieldname": "tool", "fieldtype": "Data", "width": 110},
		{"label": _("Previews"), "fieldname": "previews", "fieldtype": "Int", "width": 100},
		{"label": _("Refused files"), "fieldname": "failed", "fieldtype": "Int", "width": 110},
		{"label": _("Imports"), "fieldname": "imports", "fieldtype": "Int", "width": 100},
		{"label": _("Quote requests"), "fieldname": "quote_requests", "fieldtype": "Int", "width": 120},
	]
