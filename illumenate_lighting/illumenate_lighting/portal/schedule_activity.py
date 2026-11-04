"""A read-only activity timeline for a fixture schedule (plan 3.11).

Built from three dealer-visible sources, newest first:

* ``Version`` records of the schedule (it tracks changes): lines added, edited and removed,
  status changes, renames and locking. Only allow-listed fields are reported, so internal fields
  such as the staff status note, privacy and collaborators never appear.
* Dealer-preference events from the portal outbox ledger (``ilL-Portal-Event``) that reference
  the schedule, e.g. "Quote ready". Staff-inbox and invitation events are never included.
* Export jobs, with priced exports hidden from users without pricing permission.

Every value is returned as plain text for the page to render with ``textContent``.
"""

import html
import json
import re

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal import site_flags
from illumenate_lighting.illumenate_lighting.portal.configuration import schedule_context

SCHEDULE = "ilL-Project-Fixture-Schedule"
EVENT = "ilL-Portal-Event"
EXPORT_JOB = "ilL-Export-Job"
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_START = 500
SOURCE_LIMIT = 100
LINE_FIELDS = {"line_id": "Type", "qty": "Quantity", "location": "Location", "notes": "Notes"}
PRICED_EXPORTS = ("PDF_PRICED", "CSV_PRICED")
EXPORT_LABELS = {
	"PDF_PRICED": "PDF with pricing",
	"PDF_NO_PRICE": "PDF without pricing",
	"CSV_PRICED": "CSV with pricing",
	"CSV_NO_PRICE": "CSV without pricing",
	"SPEC_SUBMITTAL": "Spec submittal",
	"SPEC_SUBMITTAL_FULL": "Full spec submittal",
}
NAMES_SHOWN = 5
TEXT_LIMIT = 300
TAG = re.compile(r"<[^>]*>")


def _int(value, default, low, high):
	try:
		number = int(value)
	except (TypeError, ValueError):
		return default
	return max(low, min(number, high))


def _text(value, limit=TEXT_LIMIT):
	text = " ".join(html.unescape(TAG.sub(" ", str(value or ""))).split())
	return text if len(text) <= limit else text[: limit - 1] + "…"


def _entry(at, kind, title, detail="", user=None):
	return {"at": str(at or ""), "kind": kind, "title": _text(title), "detail": _text(detail), "by": user or ""}


def _line_label(row, names, position=None):
	"""A line's type, else its 1-based position (``position`` is the 0-based row index)."""
	if isinstance(row, dict):
		label = row.get("line_id") or row.get("fixture_model_number") or row.get("manufacturer_name")
		if label:
			return str(label)
		number = row.get("idx")
	else:
		if names.get(row):
			return names[row]
		number = position + 1 if isinstance(position, int) else None
	return _("Line {0}").format(number) if isinstance(number, int) else _("a line")


def _labels(labels):
	shown = ", ".join(labels[:NAMES_SHOWN])
	if len(labels) > NAMES_SHOWN:
		shown += " " + _("and {0} more").format(len(labels) - NAMES_SHOWN)
	return shown


def _value(value):
	return _text(value, 60) if value not in (None, "") else _("(empty)")


def _version_entries(version, names):
	try:
		data = json.loads(version.get("data") or "{}")
	except ValueError:
		return []
	if not isinstance(data, dict):
		return []
	at, user, entries = version.get("creation"), version.get("owner"), []
	for change in data.get("changed") or []:
		if not isinstance(change, list | tuple) or len(change) < 3:
			continue
		field, _old, new = change[:3]
		if field == "status":
			from illumenate_lighting.illumenate_lighting.portal.status import schedule_status_label

			entries.append(_entry(at, "status", _("Status changed to {0}").format(schedule_status_label(new)), "", user))
		elif field == "schedule_name":
			entries.append(_entry(at, "renamed", _("Renamed to {0}").format(_value(new)), "", user))
		elif field == "is_locked" and str(new) in ("1", "True", "true"):
			entries.append(_entry(at, "locked", _("Version locked"), "", user))
	for key, kind, title in (
		("added", "line_added", "{0} line(s) added"),
		("removed", "line_removed", "{0} line(s) removed"),
	):
		rows = [row[1] for row in data.get(key) or [] if isinstance(row, list | tuple) and len(row) > 1 and row[0] == "lines"]
		if rows:
			labels = [_line_label(row, names) for row in rows]
			entries.append(_entry(at, kind, _(title).format(len(rows)), _labels(labels), user))
	edits = []
	for row in data.get("row_changed") or []:
		if not isinstance(row, list | tuple) or len(row) < 4 or row[0] != "lines":
			continue
		changes = [
			f"{_(LINE_FIELDS[change[0]])} {_value(change[1])} → {_value(change[2])}"
			for change in row[3] or []
			if isinstance(change, list | tuple) and len(change) >= 3 and change[0] in LINE_FIELDS
		]
		if changes:
			edits.append(f"{_line_label(row[2], names, row[1])}: {', '.join(changes)}")
	if edits:
		entries.append(_entry(at, "line_edited", _("{0} line(s) edited").format(len(edits)), "; ".join(edits), user))
	return entries


def _versions(schedule):
	names = {line.name: line.get("line_id") for line in schedule.get("lines") or [] if line.get("line_id")}
	versions = frappe.get_all(
		"Version",
		filters={"ref_doctype": SCHEDULE, "docname": schedule.name},
		fields=["name", "owner", "creation", "data"],
		order_by="creation desc",
		limit_page_length=SOURCE_LIMIT,
	)
	return [entry for version in versions for entry in _version_entries(version, names)]


def _events(schedule):
	from illumenate_lighting.illumenate_lighting.portal.notifications import PREFERENCE_DEFAULTS

	events = frappe.get_all(
		EVENT,
		filters={
			"reference_type": SCHEDULE,
			"reference_name": schedule.name,
			"preference": ["in", sorted(PREFERENCE_DEFAULTS)],
		},
		fields=["name", "subject", "preference", "creation"],
		order_by="creation desc",
		limit_page_length=SOURCE_LIMIT,
	)
	return [
		_entry(event.get("creation"), "notice", event.get("subject"))
		for event in events
		if event.get("preference") in PREFERENCE_DEFAULTS
	]


def _exports(schedule):
	from illumenate_lighting.illumenate_lighting.api.exports import _check_pricing_permission

	filters = {"schedule": schedule.name}
	priced = _check_pricing_permission()
	if not priced:
		filters["export_type"] = ["not in", list(PRICED_EXPORTS)]
	jobs = frappe.get_all(
		EXPORT_JOB,
		filters=filters,
		fields=["name", "export_type", "status", "requested_by", "created_on"],
		order_by="created_on desc",
		limit_page_length=SOURCE_LIMIT,
	)
	entries = []
	for job in jobs:
		kind = job.get("export_type")
		if kind in PRICED_EXPORTS and not priced:
			continue
		label = _(EXPORT_LABELS[kind]) if kind in EXPORT_LABELS else str(kind or "")
		status = str(job.get("status") or "").replace("_", " ").title()
		entries.append(_entry(job.get("created_on"), "export", _("Export: {0}").format(label), status, job.get("requested_by")))
	return entries


def _names(entries):
	users = sorted({entry["by"] for entry in entries if entry["by"]})
	if not users:
		return {}
	rows = frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"])
	return {row.get("name"): row.get("full_name") or "" for row in rows}


def _display(value):
	formatter = getattr(frappe.utils, "format_datetime", None)
	if formatter and value:
		try:
			return str(formatter(value))
		except Exception:
			return value
	return value


@frappe.whitelist()
def schedule_activity(schedule_name, start=None, limit=None):
	"""``{"success", "entries": [{at, at_display, kind, title, detail, by_name}], "has_more", "next_start"}``."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to view schedule activity"), frappe.PermissionError)
	if not site_flags.activity_timeline_enabled():
		frappe.throw(_("The activity timeline is turned off"))
	start = _int(start, 0, 0, MAX_START)
	limit = _int(limit, DEFAULT_LIMIT, 1, MAX_LIMIT)
	schedule = schedule_context(schedule_name)
	entries = _versions(schedule) + _events(schedule) + _exports(schedule)
	entries.sort(key=lambda entry: entry["at"], reverse=True)
	page = entries[start : start + limit]
	names = _names(page)
	for entry in page:
		user = entry.pop("by")
		# Never the account's email: an unknown name stays blank.
		entry["by_name"] = names.get(user, "") if user else ""
		entry["at_display"] = _display(entry["at"])
	has_more = len(entries) > start + limit and start + limit < MAX_START
	return {
		"success": True,
		"entries": page,
		"has_more": has_more,
		"next_start": start + limit if has_more else None,
	}
