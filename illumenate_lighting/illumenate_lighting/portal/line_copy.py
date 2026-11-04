"""Copy schedule lines to another schedule (plan 3.2).

Copies follow the reorder policy (``line_intent.intent_values``): a configured line keeps its
canonical request and is marked Pending, while built Items, BOMs, configured artifacts and
prices are cleared so the target schedule recomputes them against current engineering.
Line documents are copied through ``line_documents.clone``. Included power-supply lines travel
with their owner line. A power-supply line copied on its own becomes an ordinary accessory line.
"""

import json
import uuid

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
from illumenate_lighting.illumenate_lighting.portal import site_flags
from illumenate_lighting.illumenate_lighting.portal.configuration import resolve_line, schedule_context

SCHEDULE = "ilL-Project-Fixture-Schedule"
OWNER_FIELD = "power_supply_for_line"
EDITABLE_STATUSES = ("DRAFT", "READY")
MAX_LINES = 100
MAX_TARGETS = 100
EXCLUDE = frozenset(
	{"name", "idx", "parent", "parenttype", "parentfield", "doctype", "creation", "modified", "modified_by", "owner"}
)


def _require_enabled():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to copy schedule lines"), frappe.PermissionError)
	if not site_flags.line_copy_enabled():
		frappe.throw(_("Copying lines between schedules is turned off"))


def _keys(line_keys):
	if isinstance(line_keys, str):
		try:
			line_keys = json.loads(line_keys)
		except ValueError:
			line_keys = [line_keys]
	if not isinstance(line_keys, list) or not line_keys or len(line_keys) > MAX_LINES:
		frappe.throw(_("Choose between 1 and {0} lines").format(MAX_LINES))
	if any(not isinstance(key, str) or not key.strip() for key in line_keys):
		frappe.throw(_("Choose lines by their line key"))
	return list(dict.fromkeys(key.strip() for key in line_keys))


def _editable(schedule):
	if schedule.get("is_locked"):
		frappe.throw(_("This schedule version is locked. Create a new version to make changes."))
	if schedule.get("status") not in EDITABLE_STATUSES:
		frappe.throw(_("Lines can only be copied into a Draft or Ready schedule"))


def _copy(target, line, line_key, owner_key=None):
	from illumenate_lighting.illumenate_lighting.portal.line_intent import intent_values

	values = intent_values(line, EXCLUDE)
	values["line_key"] = line_key
	if owner_key:
		values[OWNER_FIELD] = owner_key
	elif line.get(OWNER_FIELD):
		# A supply copied without its owner becomes an ordinary accessory line.
		values[OWNER_FIELD] = None
		values["power_supply_qty_per_build"] = None
	return target.append("lines", values)


def copy_into(source, keys, target):
	"""Append copies of the ``keys`` lines of ``source`` to ``target`` (unsaved).

	Returns ``(pairs, new_keys)``: every (source line, copied line) pair, including power-supply
	lines that travel with their owner, and the keys of the copied selected lines.
	"""
	try:
		chosen = {resolve_line(source, key).name for key in keys}
	except ValueError as exc:
		frappe.throw(str(exc))
	chosen_keys = {line.get("line_key") for line in source.lines if line.name in chosen and line.get("line_key")}
	pairs, new_keys = [], []
	for line in source.lines:
		if line.name not in chosen:
			continue
		if line.get(OWNER_FIELD) and line.get(OWNER_FIELD) in chosen_keys:
			continue  # copied below with its owner line
		new_line = _copy(target, line, uuid.uuid4().hex)
		pairs.append((line, new_line))
		new_keys.append(new_line.line_key)
		if not line.get("line_key"):
			continue
		for power in source.lines:
			if power.get(OWNER_FIELD) == line.line_key:
				pairs.append((power, _copy(target, power, uuid.uuid4().hex, owner_key=new_line.line_key)))
	return pairs, new_keys


def clone_documents(source, target, pairs):
	from illumenate_lighting.illumenate_lighting.portal.line_documents import clone

	for old, new in pairs:
		clone(source.name, old, target.name, new)


@frappe.whitelist(methods=["POST"])
@atomic_build
def copy_lines(source_schedule, line_keys, target_schedule, expected_modified=None):
	"""Append copies of ``line_keys`` from ``source_schedule`` to ``target_schedule``.

	All or nothing: an unknown line, a locked or non-editable target, or a target changed since
	``expected_modified`` copies nothing.
	"""
	_require_enabled()
	keys = _keys(line_keys)
	if not source_schedule or not target_schedule:
		frappe.throw(_("Choose a source and a target schedule"))
	if source_schedule == target_schedule:
		frappe.throw(_("Use Duplicate to copy a line within this schedule"))
	source = schedule_context(source_schedule)
	target = schedule_context(target_schedule, write=True, lock=True)
	_editable(target)
	if expected_modified not in (None, "") and str(target.modified) != str(expected_modified):
		frappe.throw(_("The target schedule changed. Reload and try again."))
	pairs, new_keys = copy_into(source, keys, target)
	target.save(ignore_permissions=True)
	clone_documents(source, target, pairs)
	return {
		"success": True,
		"schedule": target.name,
		"line_keys": new_keys,
		"copied": len(pairs),
		"modified": str(target.modified),
	}


@frappe.whitelist()
def copy_targets(source_schedule):
	"""Draft or Ready schedules, other than ``source_schedule``, the user may edit."""
	_require_enabled()
	schedule_context(source_schedule)
	from illumenate_lighting.illumenate_lighting.portal.access import can_edit_schedule

	rows = frappe.get_list(
		SCHEDULE,
		filters={"status": ["in", EDITABLE_STATUSES], "is_locked": 0, "name": ["!=", source_schedule]},
		fields=[
			"name",
			"schedule_name",
			"status",
			"modified",
			"owner",
			"ill_project",
			"customer",
			"inherits_project_privacy",
			"is_private",
		],
		order_by="modified desc",
		limit_page_length=MAX_TARGETS,
	)
	rows = [row for row in rows if can_edit_schedule(row)]
	projects = {
		project.name: project.project_name
		for project in frappe.get_all(
			"ilL-Project",
			filters={"name": ["in", sorted({row.ill_project for row in rows if row.ill_project})]},
			fields=["name", "project_name"],
		)
	} if rows else {}
	return {
		"success": True,
		"schedules": [
			{
				"value": row.name,
				"label": row.schedule_name or row.name,
				"project": projects.get(row.ill_project) or row.ill_project or "",
				"status": row.status,
				"modified": str(row.modified),
			}
			for row in rows
		],
	}
