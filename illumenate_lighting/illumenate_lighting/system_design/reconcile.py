# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Line fingerprints and design-versus-schedule diffs (plan H8.4, WP-2.5).

Every saved design stores ``{line key: {"fingerprint", "qty"}}`` for the schedule it was built from.
:func:`diff` compares that with the schedule now. ``packages/engine/src/reconcile.ts`` mirrors the
fingerprint byte for byte and applies the diff to the design's runs; both test the same fixture.
"""

import hashlib

from illumenate_lighting.illumenate_lighting.system_design.design_schema import round_number


def _part(value):
	return "" if value is None else str(round_number(value))


def line_fingerprint(line, builds, qty=None):
	"""SHA-256 of the H8.4 fields of one serialized line (see :func:`.expansion.serialize_line`).

	``qty`` replaces the line's quantity, so a caller can ask whether only the quantity changed.
	"""
	ref = line.get("configured") or {}
	build = ((builds.get(ref.get("doctype")) or {}).get(ref.get("name")) or {}) if ref else {}
	third = line.get("thirdParty") or {}
	parts = [
		line["key"],
		ref.get("doctype"),
		ref.get("name"),
		build.get("configHash"),
		line.get("qty") if qty is None else qty,
		third.get("wattsEach"),
		third.get("inputVoltageV"),
		third.get("voltageClass"),
		third.get("drive"),
		third.get("mA"),
		third.get("dimmingName"),
	]
	return hashlib.sha256("|".join(_part(part) for part in parts).encode("utf-8")).hexdigest()


def design_lines(lines):
	"""Lines that feed a design; write-back lines are its outputs."""
	return [line for line in lines if line.get("kind") != "writeback" and not line.get("designLineRole")]


def fingerprints(lines, builds):
	return {
		line["key"]: {"fingerprint": line_fingerprint(line, builds), "qty": line.get("qty") or 0}
		for line in design_lines(lines)
	}


def _assignments(runs):
	return [
		{"runKey": run["key"], **run["assignment"]} for run in runs if isinstance(run.get("assignment"), dict)
	]


def diff(stored, lines, builds, runs=()):
	"""``{added, removed, changed, qty, in_sync}`` between a saved design and the schedule now.

	- **removed**: in the design, not the schedule; lists the runs and assignments that will drop.
	- **added**: in the schedule, not the design; its runs arrive unassigned.
	- **changed**: same key, different build or dealer data; runs are replaced, assignments kept by run.
	- **qty**: same key, only the quantity moved; copies are added or removed from the end.
	"""
	stored = stored or {}
	runs_by_line = {}
	for run in runs or ():
		runs_by_line.setdefault(run.get("lineKey"), []).append(run)
	current = {line["key"]: line for line in design_lines(lines)}
	added, changed, qty = [], [], []
	for key, line in current.items():
		label = {"key": key, "lineId": line.get("lineId")}
		if key not in stored:
			added.append(label)
			continue
		entry = stored[key]
		saved = entry.get("fingerprint") if isinstance(entry, dict) else entry
		if saved == line_fingerprint(line, builds):
			continue
		old_qty = entry.get("qty") if isinstance(entry, dict) else None
		if old_qty is not None and saved == line_fingerprint(line, builds, qty=old_qty):
			qty.append({**label, "from": old_qty, "to": line.get("qty") or 0})
		else:
			changed.append(label)
	removed = []
	for key in sorted(set(stored) - set(current)):
		dropped = sorted(runs_by_line.get(key, []), key=lambda run: run["key"])
		removed.append(
			{"key": key, "runs": [run["key"] for run in dropped], "assignments": _assignments(dropped)}
		)
	return {
		"added": added,
		"removed": removed,
		"changed": changed,
		"qty": qty,
		"in_sync": not (added or removed or changed or qty),
	}
