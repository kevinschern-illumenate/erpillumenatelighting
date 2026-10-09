# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Line fingerprints and design-versus-schedule diffs (plan H8.4).

WP-2.4 stores the fingerprints with every saved design; the diff and its dialog follow in WP-2.5.
"""

import hashlib

from illumenate_lighting.illumenate_lighting.system_design.design_schema import round_number


def _part(value):
	return "" if value is None else str(round_number(value))


def line_fingerprint(line, builds):
	"""SHA-256 of the H8.4 fields of one serialized line (see :func:`.expansion.serialize_line`)."""
	ref = line.get("configured") or {}
	build = ((builds.get(ref.get("doctype")) or {}).get(ref.get("name")) or {}) if ref else {}
	third = line.get("thirdParty") or {}
	parts = [
		line["key"],
		ref.get("doctype"),
		ref.get("name"),
		build.get("configHash"),
		line.get("qty"),
		third.get("wattsEach"),
		third.get("inputVoltageV"),
		third.get("voltageClass"),
		third.get("drive"),
		third.get("mA"),
		third.get("dimmingName"),
	]
	return hashlib.sha256("|".join(_part(part) for part in parts).encode("utf-8")).hexdigest()


def fingerprints(lines, builds):
	"""``{line key: fingerprint}`` for every line that feeds a design; write-back lines are outputs."""
	return {
		line["key"]: line_fingerprint(line, builds)
		for line in lines
		if line.get("kind") != "writeback" and not line.get("designLineRole")
	}
