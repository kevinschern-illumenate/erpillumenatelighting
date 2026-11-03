"""Undo a line delete, move or bulk edit for a few seconds (plan 3.10).

A destructive line action keeps what it removed or overwrote in a short-lived, per-user action
receipt in the cache: the full row JSON and position of every removed line, or the previous
field values of every edited line. ``undo_line_action`` re-checks access and editability like any
other edit, then re-inserts the rows with their original ``line_key`` (so their line documents,
which are keyed by schedule and line key, re-attach) or writes the old values back. It refuses a
restore that would duplicate a line key, a receipt that expired or belongs to someone else, and a
locked or no-longer-editable schedule. A receipt is used once.
"""

import json
import secrets
import time

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
from illumenate_lighting.illumenate_lighting.portal import line_copy, site_flags
from illumenate_lighting.illumenate_lighting.portal.configuration import resolve_line, schedule_context

WINDOW = 10  # seconds the Undo button is offered
GRACE = 5  # slack for the page reload and the request itself
PREFIX = "ill_portal_line_undo:"
ACTIONS = ("delete", "move", "update")
FIELDS = ("qty", "location", "line_id", "notes")
LINE_DOCUMENT = "ilL-Line-Document"
EXPIRED = "This action can no longer be undone."


def snapshot(schedule, lines):
	"""The row JSON and position of each line in ``lines``, taken before they are removed."""
	positions = {id(line): index for index, line in enumerate(schedule.lines)}
	rows = []
	for line in lines:
		values = line.as_dict() if hasattr(line, "as_dict") else dict(line)
		row = {key: value for key, value in values.items() if key not in line_copy.EXCLUDE}
		rows.append({"index": positions.get(id(line), len(schedule.lines)), "row": row})
	return rows


def previous_values(lines, values):
	"""The current value of each field in ``values`` for every (key, line), before an edit."""
	return [
		{"line_key": line.get("line_key") or key, "values": {field: line.get(field) for field in values}}
		for key, line in lines
	]


def remember(schedule, action, rows, **extra):
	"""Store an undo receipt for ``rows`` and return what the page needs to offer Undo, or None.

	Never fails the action it follows: a cache problem only means no Undo is offered.
	"""
	if not rows:
		return None
	try:
		if not site_flags.undo_enabled():
			return None
		token = secrets.token_urlsafe(18)
		receipt = {
			"user": frappe.session.user,
			"schedule": schedule.name,
			"action": action,
			"rows": rows,
			"expires": time.time() + WINDOW + GRACE,
			**extra,
		}
		frappe.cache().set_value(PREFIX + token, frappe.as_json(receipt), expires_in_sec=WINDOW + GRACE)
		return {"token": token, "expires_in": WINDOW, "action": action, "count": len(rows)}
	except Exception:
		frappe.log_error(title="Portal: could not record an undo receipt", message=frappe.get_traceback())
		return None


def _receipt(token):
	if not isinstance(token, str) or not token.strip() or len(token) > 64:
		frappe.throw(_(EXPIRED))
	raw = frappe.cache().get_value(PREFIX + token.strip())
	try:
		receipt = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
	except ValueError:
		receipt = None
	# Someone else's receipt reads exactly like an expired one.
	if (
		not isinstance(receipt, dict)
		or receipt.get("user") != frappe.session.user
		or receipt.get("action") not in ACTIONS
		or float(receipt.get("expires") or 0) < time.time()
	):
		frappe.throw(_(EXPIRED))
	return receipt


def _editable(schedule):
	if schedule.get("is_locked"):
		frappe.throw(_("This schedule version is locked. Create a new version to make changes."))
	if schedule.get("status") not in line_copy.EDITABLE_STATUSES:
		frappe.throw(_("Lines can only be changed in a Draft or Ready schedule"))


def _reindex(schedule):
	for index, line in enumerate(schedule.lines, start=1):
		line.idx = index


def _restore_rows(schedule, rows):
	existing = {line.get("line_key") for line in schedule.lines if line.get("line_key")}
	if any(entry["row"].get("line_key") in existing for entry in rows):
		frappe.throw(_("A line you are restoring is already in this schedule. Reload to see the latest version."))
	for entry in sorted(rows, key=lambda item: int(item.get("index") or 0)):
		schedule.append("lines", entry["row"])
		row = schedule.lines.pop()
		schedule.lines.insert(min(max(int(entry.get("index") or 0), 0), len(schedule.lines)), row)
	_reindex(schedule)


def _withdraw(target, keys):
	"""Remove the copies a move added to ``target`` and retire their cloned line documents."""
	keys = set(keys or [])
	present = {line.get("line_key") for line in target.lines}
	if not keys or not keys <= present:
		frappe.throw(_("The moved lines changed in the other schedule. Reload to see the latest version."))
	target.lines = [line for line in target.lines if line.get("line_key") not in keys]
	_reindex(target)
	target.save(ignore_permissions=True)
	frappe.db.set_value(
		LINE_DOCUMENT, {"schedule": target.name, "line_key": ["in", sorted(keys)], "active": 1}, "active", 0
	)


def _restore_values(schedule, rows):
	from illumenate_lighting.illumenate_lighting.portal.line_edit import apply_line_data

	for entry in rows:
		try:
			line = resolve_line(schedule, entry.get("line_key"))
		except ValueError:
			frappe.throw(_("A line you edited is no longer in this schedule. Reload to see the latest version."))
		applied = entry.get("applied") or {}
		if any(str(line.get(field) or "") != str(value or "") for field, value in applied.items()):
			frappe.throw(_("A line you edited changed again since. Reload to see the latest version."))
		values = {
			field: ("" if value is None and field != "qty" else value)
			for field, value in (entry.get("values") or {}).items()
			if field in FIELDS
		}
		apply_line_data(schedule, line, values)


@frappe.whitelist(methods=["POST"])
@atomic_build
def undo_line_action(token):
	"""Reverse the line action recorded under ``token`` (plan 3.10). Single use."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to edit schedule lines"), frappe.PermissionError)
	if not site_flags.undo_enabled():
		frappe.throw(_("Undo is turned off"))
	receipt = _receipt(token)
	schedule = schedule_context(receipt["schedule"], write=True, lock=True)
	_editable(schedule)
	action, rows = receipt["action"], receipt.get("rows") or []
	if action == "update":
		_restore_values(schedule, rows)
	else:
		target = None
		if action == "move":
			target = schedule_context(receipt.get("target"), write=True, lock=True)
			_editable(target)
		_restore_rows(schedule, rows)
		if target is not None:
			_withdraw(target, receipt.get("target_keys"))
	schedule.save(ignore_permissions=True)
	frappe.cache().delete_value(PREFIX + token.strip())
	return {
		"success": True,
		"schedule": schedule.name,
		"action": action,
		"count": len(rows),
		"modified": str(schedule.modified),
	}
