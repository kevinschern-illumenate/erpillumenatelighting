"""Readable multi-run group part numbers, shaped like a configured part number.

A group's runs share every specification, so they share the configured part
number up to its length. The group number keeps that prefix, puts the total of
all runs in the length position (inches; square feet for LED Sheet areas) and
replaces the run's feed segments with ``GRP(XXXX)``:

    ILL-SH01-HD-DR-30-HO-FR-SM-WH-144.0-GRP(A1B2)
    LS01-DR-30-HO-AD-WH-48SF-GRP(A1B2)

``XXXX`` comes from the group's content hash, so one group has one number on
the schedule, the desk dialog, the Quotation and the Sales Order. It grows
past four characters only when another group already holds the code.

The engineering record (``ilL-Configured-Group``) keeps its internal
``ILL-GRP-<hash>`` Item; this number names the sellable bundle of its runs.
"""

import frappe

CODE_LENGTH = 4
GROUP_DOCTYPE = "ilL-Configured-Group"
LINE_DOCTYPE = "ilL-Child-Fixture-Schedule-Line"
LINEAR = "Linear Fixture"
SHEET = "LED Sheet"


def _number(value):
	"""Whole numbers without a decimal, otherwise one decimal (as tape/neon part numbers)."""
	value = round(float(value), 1)
	return str(int(value)) if value == int(value) else f"{value:.1f}"


def _linear_inches(mm):
	"""Linear part numbers always carry one decimal, e.g. ``120.0``."""
	return f"{float(mm) / 25.4:.1f}"


def _segments(member):
	return member.get("geometry", {}).get("segments") or []


def _requested_mm(member):
	return sum(float(s.get("requested_length_mm") or 0) for s in _segments(member))


def _manufactured_mm(member):
	computed = (member.get("build") or {}).get("computed") or {}
	pieces = [s.get("manufacturable_length_mm") for s in computed.get("segments") or []]
	if pieces and all(p is not None for p in pieces):
		return sum(float(p) for p in pieces)
	for key in (
		"manufacturable_length_mm",
		"total_manufacturable_length_mm",
		"manufacturable_overall_length_mm",
	):
		if computed.get(key):
			return float(computed[key])
	return _requested_mm(member)


def _length_tokens(family, member):
	"""Every way the run's own part number may have written its length."""
	if family == LINEAR:
		mm = _requested_mm(member)
		return {_linear_inches(mm), _linear_inches(round(mm))}
	computed = (member.get("build") or {}).get("computed") or {}
	tokens = {_number(_manufactured_mm(member) / 25.4), "xx"}
	if computed.get("manufacturable_length_mm"):
		tokens.add(_number(float(computed["manufacturable_length_mm"]) / 25.4))
	inches = [s.get("manufacturable_length_in") for s in computed.get("segments") or []]
	if inches and all(i is not None for i in inches):
		tokens.add(_number(sum(float(i) for i in inches)))
	return tokens


def run_prefix(family, member):
	"""The run's configured part number up to (not including) its length, or ``None``."""
	part_number = str((member.get("build") or {}).get("part_number") or "").strip()
	if not part_number:
		return None
	if family == SHEET:
		return part_number  # Sheet numbers carry no length or feed segments.
	found = [part_number.rfind(f"-{token}-") for token in _length_tokens(family, member)]
	found = [index for index in found if index > 0]
	return part_number[: max(found)] if found else None


def total_length(family, members):
	if family == SHEET:
		area = sum(
			float(m["geometry"].get("coverage_width_ft") or 0)
			* float(m["geometry"].get("coverage_height_ft") or 0)
			for m in members
		)
		return _number(area) + "SF"
	if family == LINEAR:
		return _linear_inches(sum(_requested_mm(m) for m in members))
	return _number(sum(_manufactured_mm(m) for m in members) / 25.4)


def base(build):
	"""``{prefix}-{total length}``: everything before ``-GRP(...)``."""
	family = build["request"]["family"]
	members = build["members"]
	prefix = next((p for p in (run_prefix(family, m) for m in members) if p), None)
	if not prefix:
		# A run without a readable part number still gets a stable, sellable code.
		prefix = str(build["request"].get("template") or "GROUP").strip().upper().replace(" ", "-")
	return f"{prefix}-{total_length(family, members)}"


def _owner(code):
	"""``(exists, group)`` for an Item code."""
	if not frappe.db.exists("Item", code):
		return False, None
	return True, frappe.db.get_value("Item", code, "ill_configured_group")


def is_available(code, group_name, accept=None):
	"""Free, or already this group's own Item (and acceptable to ``accept``)."""
	exists, owner = _owner(code)
	if exists and (owner != group_name or (accept is not None and not accept(code))):
		return False
	return not frappe.db.exists(
		LINE_DOCTYPE, {"group_part_number": code, "configured_group": ["!=", group_name]}
	)


def for_group(group, build=None, accept=None):
	"""The group's part number: four hash characters, more only on a collision."""
	if build is None:
		from illumenate_lighting.illumenate_lighting.api.fixture_group_bom import snapshot

		build = snapshot(group)
	stem = base(build)
	digest = str(group.config_hash or "").upper()
	for size in range(CODE_LENGTH, len(digest) + 1):
		code = f"{stem}-GRP({digest[:size]})"
		if is_available(code, group.name, accept):
			return code
	raise ValueError("A unique group part number could not be generated; engineering review is required")


def belongs_to(code, group_name):
	exists, owner = _owner(code)
	return exists and owner == group_name


def assign(schedule):
	"""Give every group line its group's part number.

	A line keeps the number it has while it holds the same group, whatever
	format that number was made in, so quoted and ordered codes never change.
	A new or changed group receives the group's part number.
	"""
	before = schedule.get_doc_before_save() if hasattr(schedule, "get_doc_before_save") else None
	previous = {
		row.name: row.get("configured_group") for row in (before.get("lines") if before else None) or []
	}
	numbers = {}
	for line in schedule.get("lines") or []:
		group = line.get("configured_group")
		if not group:
			if line.get("group_part_number"):
				line.group_part_number = None
			continue
		current = line.get("group_part_number")
		keep = current and (previous.get(line.name, group) == group or belongs_to(current, group))
		if not keep:
			if group not in numbers:
				numbers[group] = for_group(frappe.get_doc(GROUP_DOCTYPE, group))
			current = line.group_part_number = numbers[group]
		line.ill_item_code = current
