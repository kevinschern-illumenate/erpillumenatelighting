"""Edit, delete or move several schedule lines at once (plan 3.3).

Every selected line goes through the same single-line validator as the row editor
(``line_edit.apply_line_data``) on one schedule document, which is saved once. The request is
all or nothing: if any line fails, nothing is saved and every failure is reported against
its line. Moving to another schedule copies the lines with the reorder policy
(``line_copy.copy_into``) and then removes them from this schedule in the same transaction.
"""

import json

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
from illumenate_lighting.illumenate_lighting.portal import line_copy, site_flags
from illumenate_lighting.illumenate_lighting.portal.configuration import resolve_line, schedule_context
from illumenate_lighting.illumenate_lighting.portal.schedule_lines import require_fresh

FIELDS = ("qty", "location", "line_id", "notes")
TEXT_LIMITS = {"line_id": 140, "location": 140, "notes": 2000}
ACTIONS = ("update", "delete", "move")
MAX_QTY = 1_000_000


def _changes(changes):
	if isinstance(changes, str):
		try:
			changes = json.loads(changes)
		except ValueError:
			frappe.throw(_("Invalid changes"))
	if not isinstance(changes, dict):
		frappe.throw(_("Invalid changes"))
	action = changes.get("action") or "update"
	if action not in ACTIONS:
		frappe.throw(_("Unsupported bulk action"))
	if action == "delete":
		return action, {}
	if action == "move":
		target = changes.get("target_schedule")
		if not isinstance(target, str) or not target.strip():
			frappe.throw(_("Choose a schedule to move the lines to"))
		return action, {"target_schedule": target.strip(), "target_modified": changes.get("target_modified")}
	values = {}
	for field in FIELDS:
		if field not in changes:
			continue
		value = changes[field]
		if field == "qty":
			try:
				number = float(str(value).strip())
			except ValueError:
				number = 0
			if not number.is_integer() or number < 1 or number > MAX_QTY:
				frappe.throw(_("Quantity must be a whole number of at least 1"))
			values[field] = int(number)
			continue
		value = "" if value is None else value
		if not isinstance(value, (str, int, float)):
			frappe.throw(_("Invalid value for {0}").format(field))
		value = str(value) if field == "notes" else str(value).strip()
		if len(value) > TEXT_LIMITS[field]:
			frappe.throw(_("{0} is limited to {1} characters").format(field, TEXT_LIMITS[field]))
		values[field] = value
	if not values:
		frappe.throw(_("Choose at least one field to change"))
	return action, values


def _editable(schedule):
	if schedule.get("is_locked"):
		frappe.throw(_("This schedule version is locked. Create a new version to make changes."))
	if schedule.get("status") not in line_copy.EDITABLE_STATUSES:
		frappe.throw(_("Lines can only be changed in a Draft or Ready schedule"))


def _label(line, key):
	return line.get("line_id") or line.get("line_key") or key


def _error_message(exc):
	return str(exc) or _("This line could not be changed")


@frappe.whitelist(methods=["POST"])
@atomic_build
def bulk_update_lines(schedule, line_keys, changes, expected_modified=None):
	"""Apply ``changes`` to every line in ``line_keys`` of ``schedule``, all or nothing.

	``changes`` is ``{"qty"|"location"|"line_id"|"notes": value, ...}`` for an update,
	``{"action": "delete"}`` or ``{"action": "move", "target_schedule": name, "target_modified": ...}``.
	A failure returns ``{"success": False, "errors": [{"line_key", "line", "error"}]}`` and saves nothing.
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to edit schedule lines"), frappe.PermissionError)
	if not site_flags.bulk_edit_enabled():
		frappe.throw(_("Bulk editing is turned off"))
	keys = line_copy._keys(line_keys)
	action, values = _changes(changes)
	doc = schedule_context(schedule, write=True, lock=True)
	_editable(doc)
	require_fresh(doc, expected_modified)

	errors, lines = [], []
	for key in keys:
		try:
			lines.append((key, resolve_line(doc, key)))
		except ValueError as exc:
			errors.append({"line_key": key, "line": key, "error": _error_message(exc)})
	if errors:
		return {"success": False, "error": _("Some lines could not be changed"), "errors": errors}

	result = {"success": True, "schedule": doc.name, "action": action, "count": len(lines)}
	if action == "update":
		from illumenate_lighting.illumenate_lighting.portal.line_edit import apply_line_data

		for key, line in lines:
			try:
				apply_line_data(doc, line, values)
			except Exception as exc:
				if isinstance(exc, frappe.PermissionError):
					raise
				errors.append({"line_key": key, "line": _label(line, key), "error": _error_message(exc)})
	elif action == "move":
		if values["target_schedule"] == doc.name:
			frappe.throw(_("Choose a different schedule to move the lines to"))
		target = schedule_context(values["target_schedule"], write=True, lock=True)
		line_copy._editable(target)
		if values["target_modified"] not in (None, "") and str(target.modified) != str(values["target_modified"]):
			frappe.throw(_("The target schedule changed. Reload and try again."))
		pairs, new_keys = line_copy.copy_into(doc, keys, target)
		moved = {id(old) for old, _new in pairs}
		target.save(ignore_permissions=True)
		line_copy.clone_documents(doc, target, pairs)
		doc.lines = [line for line in doc.lines if id(line) not in moved]
		result.update(target=target.name, line_keys=new_keys, count=len(pairs))
	else:
		chosen = {id(line) for _key, line in lines}
		doc.lines = [line for line in doc.lines if id(line) not in chosen]

	if errors:
		return {"success": False, "error": _("Some lines could not be changed"), "errors": errors}
	for index, line in enumerate(doc.lines, start=1):
		line.idx = index
	doc.save(ignore_permissions=True)
	result["modified"] = str(doc.modified)
	return result
