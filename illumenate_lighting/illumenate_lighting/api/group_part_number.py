"""Readable multi-run group part numbers: TEMPLATE-PROJECT-TYPE-LOCATION-XXXX.

The engineering record (``ilL-Configured-Group``) stays global and content
addressed. The part number belongs to one schedule line, because it names the
project, fixture type and location the group was configured for.
"""

import re
import secrets
import string

import frappe

SEGMENT_MAX_LENGTH = 30
SUFFIX_LENGTH = 4
LINE_DOCTYPE = "ilL-Child-Fixture-Schedule-Line"


def segment(value, limit=SEGMENT_MAX_LENGTH):
	"""Uppercase letters and digits joined by single hyphens; blank when nothing remains."""
	text = re.sub(r"[^A-Z0-9]+", "-", str(value or "").upper()).strip("-")
	return text[:limit].rstrip("-")


def prefix(template, project=None, fixture_type=None, location=None):
	"""Every part before the unique suffix; blank segments are omitted."""
	parts = [segment(template, 60), segment(project), segment(fixture_type), segment(location)]
	return "-".join(part for part in parts if part)


def is_taken(code):
	return bool(frappe.db.exists("Item", code) or frappe.db.exists(LINE_DOCTYPE, {"group_part_number": code}))


def generate(base, reserved=()):
	"""``base`` plus four random uppercase letters, drawn again only on a collision."""
	for _attempt in range(50):
		code = f"{base}-" + "".join(secrets.choice(string.ascii_uppercase) for _ in range(SUFFIX_LENGTH))
		if code not in reserved and not is_taken(code):
			return code
	raise ValueError("A unique group part number could not be generated; try again")


def project_label(schedule):
	if not schedule.get("ill_project"):
		return None
	return frappe.db.get_value("ilL-Project", schedule.ill_project, "project_name") or schedule.ill_project


def line_prefix(schedule, line, template, project=None):
	return prefix(
		template, project if project is not None else project_label(schedule), line.line_id, line.location
	)


def assign(schedule):
	"""Give every group line a part number that matches its project, type and location.

	A line keeps its number while its group and naming inputs are unchanged. A
	new group, a renamed fixture type/location/project, or a duplicated line
	(two lines sharing one number) receives a fresh suffix.
	"""
	before = schedule.get_doc_before_save() if hasattr(schedule, "get_doc_before_save") else None
	previous = {
		row.name: row.get("configured_group") for row in (before.get("lines") if before else None) or []
	}
	project = None
	used = set()
	for line in schedule.get("lines") or []:
		group = line.get("configured_group")
		if not group:
			if line.get("group_part_number"):
				line.group_part_number = None
			continue
		if project is None:
			project = project_label(schedule) or ""
		template = frappe.db.get_value("ilL-Configured-Group", group, "template")
		base = line_prefix(schedule, line, template, project)
		current = line.get("group_part_number")
		keep = (
			current
			and current.rpartition("-")[0] == base
			and current not in used
			and previous.get(line.name, group) == group
		)
		if not keep:
			current = generate(base, used)
			line.group_part_number = current
		used.add(current)
		line.ill_item_code = current
