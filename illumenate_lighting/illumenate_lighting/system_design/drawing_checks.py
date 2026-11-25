# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""The AutoCAD toolkit's ILCHECK rules on the server, for packages that never ran them (WP 1.9).

A package from AutoCAD was checked by the AutoLISP ``il-check`` (``tools/cad_toolkit/lisp/il-model.lsp``)
and ``il-check-controls`` (``il-controls.lsp``) before it was written. Packages made from a DXF upload
(and soon from Bluebeam PDFs) skip those checks, so the import runs the rules that decide whether the
quote is right here, from the ``ilq/2`` package (as ``ilq_schema.with_defaults`` returns it) and the
``cad-catalog/1`` document (``cad_catalog.cad_catalog(user)`` / ``cad_catalog.build_payload``). Codes,
refs, severities and texts are the LISP's; ``tests/portal_unit/test_drawing_checks.py`` runs both on
the cases in ``tools/system_designer/fixtures/cad/check-cases.json`` and compares them.

Pure: no Frappe import, so CI and the toolkit's tests import it directly.

Rules ported (code, severity):

- ``CATALOG_MISSING`` (error, ref ``drawing``): no catalog was given; every catalog rule is skipped,
  as in the LISP.
- ``RUN_NO_TAPE`` (error): the LISP reports a run whose whole path is jumper span (no lit piece). A
  package carries only the lit pieces (``segments``), and the ``ilq/2`` schema requires at least one,
  so the condition is not derivable from a valid package: the LISP's own writer would emit
  ``segments: []`` and the validator rejects it. The closest equivalent is reported: a run with no
  segments, which only an unvalidated package (an ingester's draft) can have.
- ``TEMPLATE_DISCONTINUED`` (error): the style's template, or a kit style's tape template, is not in
  the catalog (``il-cat-template``: tape families look in ``templates`` and match the family too,
  ``Linear Fixture`` in ``fixture_templates``, ``Extrusion Kit`` in ``kit_templates``; any other
  family is never found). Like the LISP, the geometry rules below are skipped for such a run.
- ``BEND_RADIUS`` (error): the run's smallest arc radius (the smallest ``min_arc_radius_in`` of its
  segments) is under the drawn variant's ``min_bend_radius_in``. The variant is ``il-cat-variant``'s:
  scored on ``environment_rating``, ``cct`` and ``output_level`` against the (kit tape's) selections,
  first best wins, the template's ``default_variant`` only when every variant conflicts.
- ``PROFILE_NOT_CURVE_CAPABLE`` (error): the run has an arc and the style template's profile (a kit's
  or a linear fixture's ``profile``) is not ``curve_capable: true``.
- ``TAPE_WIDER_THAN_PROFILE`` (error): the variant's ``width_in`` is over the profile's ``width_in``.
- ``PSU_OVERLOAD`` (warning): per PSU with an ``item_code`` that is a catalog driver with ``rated_w``
  (the last driver with that code, as the LISP's ``foreach`` keeps it), the runs it lists load
  ``round((snapped_in / 12) * w_per_ft, 2)`` W each, where ``snapped_in`` sums each segment's cut-snapped
  length (``il-cut-snap``: whole ``cut_mm`` increments, at least one, unless the variant is
  ``free_cut``), times the run's stacked ``copies``; runs without a tape variant or ``w_per_ft`` add nothing. Over when the total (summed
  in the LISP's order) is over ``rated_w * usable_load_factor`` (factor 1.0 when absent).
- ``CONTROL_UNKNOWN`` (error): a control's ``item_code`` is not in the catalog's ``controllers``.
- ``DMX_UNIVERSE_FULL`` / ``DMX_ADDRESS_OVERLAP`` (errors): the DMX patch preview (``il-dmx-patch``):
  receivers (catalog ``receives_dmx: true``) sorted by id, per universe fixed starts keep theirs and
  ``auto`` ones take the next free block of ``dmx_footprint`` channels (1 when absent); a block ending
  past 512 is full, and two blocks in one universe that share a channel are reported on the smaller id.
- ``PROTOCOL_MISMATCH`` (error): a zone's control (found in the package, and in the catalog) has no
  port with the zone's port name, or the port's ``protocol`` is not the zone method's protocol
  (method ``none`` wants none).

Where the package differs from the LISP model:

- Lengths and radii: the LISP rounds each lit piece's length and smallest arc radius to 4 decimals
  (``il-path-length``) before it snaps and compares; the package carries those rounded numbers, and
  values from other front ends are rounded the same way here, so the arithmetic is identical.
- DMX addresses: the LISP writes a control's ``dmx`` only when it has a universe, so a start address
  set without a universe is not in the package; such a control patches as universe 1, ``auto``.
- Ids: a valid package has unique, non-empty run and control ids, so the LISP's ``RUN_MISSING_ID`` /
  ``RUN_DUPLICATE_ID`` paths (issues on a handle or a repeated id) do not arise.

Not ported (geometry-only or drawing-housekeeping hints the import decides itself): ``CATALOG_STALE``,
``SCALE_UNVERIFIED``, ``RUN_MISSING_ID``, ``RUN_DUPLICATE_ID``, ``RUN_MISSING_TYPE``, ``RUN_NO_ROOM``,
``JUMPER_SPAN_AT_END``, ``RUN_NO_STYLE``, ``CUT_SNAP``, ``TAPE_RUN_TOO_LONG``, ``RUN_UNCONNECTED``,
``WIRE_UNKNOWN_END``, ``CONTROL_NO_SIGNAL``, ``CONTROL_UNKNOWN_SOURCE``, ``ZONE_EMPTY``,
``RUN_IN_TWO_ZONES``, ``ZONE_NO_CONTROL``, ``ZONE_UNKNOWN_CONTROL``, ``DATA_TOO_LONG``.

Overrides (``package["check"]["overrides"]``): :func:`apply_overrides` drops the issues an override
with the same code and ref covers, and :func:`issue_counts` counts errors and warnings the way the
LISP's ``il-issue-counts`` does (an overridden issue counts as neither, whatever its severity).
"""

import math

PORTED_CODES = frozenset(
	{
		"CATALOG_MISSING",
		"RUN_NO_TAPE",
		"TEMPLATE_DISCONTINUED",
		"BEND_RADIUS",
		"PROFILE_NOT_CURVE_CAPABLE",
		"TAPE_WIDER_THAN_PROFILE",
		"PSU_OVERLOAD",
		"CONTROL_UNKNOWN",
		"DMX_UNIVERSE_FULL",
		"DMX_ADDRESS_OVERLAP",
		"PROTOCOL_MISMATCH",
	}
)

TAPE_FAMILIES = ("LED Tape", "COB Tape", "LED Neon")
MM_PER_IN = 25.4
DMX_CHANNELS = 512

# Zone method -> the protocol a control port must send (*il-zone-protocols*; "none" wants none).
ZONE_PROTOCOLS = {
	method: method
	for method in (
		"DMX512",
		"CRMX-wireless",
		"0-10V",
		"DALI-2",
		"Lutron-QS",
		"Lutron-EcoSystem",
		"phase-forward",
		"phase-reverse",
	)
}


# --- LISP numerics (il-util.lsp, il-math.lsp) ---------------------------------------------------


def _number(value):
	return isinstance(value, (int, float)) and not isinstance(value, bool)


def _round_even(x):
	"""``il-round-even``: Python's round() to a whole number."""
	low = math.floor(x)
	diff = x - low
	if diff < 0.5:
		return low
	if diff > 0.5:
		return low + 1
	return low if low % 2 == 0 else low + 1


def round_py(x, digits):
	"""``il-round-py``: half to even on the scaled value (within 1e-9), else half up."""
	scale = 10.0**digits
	scaled = x * scale
	low = math.floor(scaled)
	if abs(scaled - low - 0.5) < 1e-9:
		return _round_even(scaled) / scale
	return math.floor(scaled + 0.5) / scale


def _round(x, digits):
	"""``il-round``: half away from zero, for display."""
	scale = 10.0**digits
	if x < 0:
		return -(math.floor(-x * scale + 0.5) / scale)
	return math.floor(x * scale + 0.5) / scale


def num_str(x, digits):
	"""``il-num->str``: at most DIGITS decimals, no trailing zeros; integers as they are."""
	if isinstance(x, int) and not isinstance(x, bool):
		return str(x)
	text = f"{_round(float(x), digits):.{int(digits)}f}"
	if "." in text:
		text = text.rstrip("0").rstrip(".")
	return "0" if text == "-0" else text


def _il_str(value):
	"""``il-str``."""
	if value is None:
		return ""
	if isinstance(value, str):
		return value
	if isinstance(value, int) and not isinstance(value, bool):
		return str(value)
	if isinstance(value, float):
		return num_str(value, 4)
	return str(value)


def _itoa(value):
	return str(int(value)) if _number(value) and float(value).is_integer() else str(value)


def cut_snap_in(length_in, cut_mm, free_cut):
	"""``il-cut-snap``'s ``mfg_in``: the length built in whole cut increments (at least one)."""
	requested = length_in * MM_PER_IN
	if free_cut or not _number(cut_mm) or cut_mm <= 0 or requested <= 0:
		return round_py(length_in, 4)
	increments = max(1, math.floor(float(requested) / cut_mm + 1e-9))
	return round_py((increments * cut_mm) / MM_PER_IN, 4)


def run_watts(length_in, w_per_ft):
	"""``il-run-watts``."""
	return round_py((length_in / 12.0) * w_per_ft, 2)


# --- Catalog lookups (il-catalog.lsp, il-controls.lsp) ------------------------------------------


def _j(obj, key):
	return obj.get(key) if isinstance(obj, dict) else None


def _items(value):
	return value if isinstance(value, list) else []


def _first(items, key, value):
	for item in _items(items):
		if _j(item, key) == value:
			return item
	return None


def cat_template(catalog, family, code):
	"""``il-cat-template``: the template FAMILY/CODE offers, or None."""
	if family in TAPE_FAMILIES:
		section = "templates"
	elif family == "Linear Fixture":
		section = "fixture_templates"
	elif family == "Extrusion Kit":
		section = "kit_templates"
	else:
		return None
	for item in _items(_j(catalog, section)):
		if _j(item, "code") == code and (section != "templates" or _j(item, "family") == family):
			return item
	return None


def cat_variant(template, selections):
	"""``il-cat-variant``: the variant matching SELECTIONS, the template default otherwise."""
	best, best_score, default = None, -1, None
	for variant in _items(_j(template, "variants")):
		if _j(variant, "id") == _j(template, "default_variant"):
			default = variant
		score = 0
		for key in ("environment_rating", "cct", "output_level"):
			wanted, offered = _j(selections, key), _j(variant, key)
			if wanted is None or offered is None:
				continue
			score = score + 1 if wanted == offered else -100
		if score > best_score:
			best, best_score = variant, score
	return best if best_score >= 0 else default


def style_tape(style):
	"""``il-style-tape``: the style itself, or a kit style's tape."""
	return _j(style, "tape") if _j(style, "family") == "Extrusion Kit" else style


def style_variant(catalog, style):
	"""``il-style-variant``: the tape variant a style draws with (None for linear fixtures)."""
	tape = style_tape(style)
	if tape is not None and _j(tape, "family") in TAPE_FAMILIES:
		template = cat_template(catalog, _j(tape, "family"), _j(tape, "template"))
		if template is not None:
			return cat_variant(template, _j(tape, "selections"))
	return None


def style_profile(catalog, style):
	"""``il-style-profile``: the kit's or the linear template's profile."""
	template = cat_template(catalog, _j(style, "family"), _j(style, "template"))
	if template is not None and _j(template, "profile") is not None:
		return _first(_j(catalog, "profiles"), "code", _j(template, "profile"))
	return None


def cat_control(catalog, code):
	"""``il-cat-control``."""
	return _first(_j(catalog, "controllers"), "code", code)


# --- Runs -------------------------------------------------------------------------------------


def _segment_lengths(run):
	return [
		round_py(float(_j(segment, "path_length_in") or 0.0), 4) for segment in _items(run.get("segments"))
	]


def min_arc_radius_in(run):
	"""The run's smallest arc radius (``il-run-geometry``), None when it is straight."""
	radii = [
		round_py(float(_j(segment, "min_arc_radius_in")), 4)
		for segment in _items(run.get("segments"))
		if _number(_j(segment, "min_arc_radius_in"))
	]
	return min(radii) if radii else None


def run_load_w(run, catalog):
	"""The run's watts as ``il-run-hint`` shows them, or None (no tape variant, no W/ft)."""
	style = run.get("style")
	variant = style_variant(catalog, style) if isinstance(style, dict) else None
	if variant is None:
		return None
	cut, free = _j(variant, "cut_mm"), _j(variant, "free_cut") is True
	snapped = 0.0
	for length in _segment_lengths(run):
		snapped = snapped + cut_snap_in(length, cut, free)
	w_per_ft = _j(variant, "w_per_ft")
	return run_watts(snapped, w_per_ft) if _number(w_per_ft) else None


def _issue(code, ref, severity, text):
	return {"code": code, "ref": ref, "severity": severity, "text": text}


def _run_issues(run, catalog):
	issues = []
	run_id = run.get("id")
	if not _items(run.get("segments")):
		issues.append(
			_issue(
				"RUN_NO_TAPE",
				run_id,
				"error",
				"The whole run is marked as jumper span; take a span off with ILJUMPER",
			)
		)
	style = run.get("style")
	if not isinstance(style, dict) or catalog is None:
		return issues
	if cat_template(catalog, _j(style, "family"), _j(style, "template")) is None:
		text = f"{_il_str(_j(style, 'template'))} is not in the current catalog"
		return [*issues, _issue("TEMPLATE_DISCONTINUED", run_id, "error", text)]
	if _j(style, "family") == "Extrusion Kit":
		tape = _j(style, "tape")
		if cat_template(catalog, _j(tape, "family"), _j(tape, "template")) is None:
			text = f"{_il_str(_j(tape, 'template'))} is not in the current catalog"
			return [*issues, _issue("TEMPLATE_DISCONTINUED", run_id, "error", text)]
	variant = style_variant(catalog, style)
	radius = min_arc_radius_in(run)
	bend = _j(variant, "min_bend_radius_in")
	if variant is not None and _number(bend) and radius is not None and radius < bend:
		issues.append(
			_issue(
				"BEND_RADIUS",
				run_id,
				"error",
				f"Arc radius {num_str(radius, 2)} in is under the tape's {num_str(bend, 2)} in minimum",
			)
		)
	profile = style_profile(catalog, style)
	if profile is not None and radius is not None and _j(profile, "curve_capable") is not True:
		text = f"{_il_str(_j(profile, 'code'))} cannot follow a curve"
		issues.append(_issue("PROFILE_NOT_CURVE_CAPABLE", run_id, "error", text))
	tape_width = _j(variant, "width_in")
	profile_width = _j(profile, "width_in")
	if profile is not None and _number(tape_width) and _number(profile_width) and tape_width > profile_width:
		issues.append(
			_issue(
				"TAPE_WIDER_THAN_PROFILE",
				run_id,
				"error",
				f"Tape is {num_str(tape_width, 3)} in wide; {_il_str(_j(profile, 'code'))} fits "
				f"{num_str(profile_width, 3)} in",
			)
		)
	return issues


def _copies_load(load, run):
	"""``il-copies-load``: a run's load times its stacked copies (LISP ``*`` keeps it a real)."""
	copies = int(run.get("copies") or 1)
	return None if load is None else (load * copies if copies > 1 else load)


def _psu_issues(package, catalog):
	issues = []
	runs = _items(package.get("runs"))
	for psu in _items(package.get("psus")):
		driver = None
		if catalog is not None and psu.get("item_code") is not None:
			for item in _items(_j(catalog, "drivers")):
				if _j(item, "code") == psu.get("item_code"):
					driver = item
		rated = _j(driver, "rated_w")
		if driver is None or not _number(rated):
			continue
		fed = _items(psu.get("runs"))
		# A stacked run's copies each load the supply.
		loads = [_copies_load(run_load_w(run, catalog), run) for run in runs if run.get("id") in fed]
		total = 0.0
		for load in reversed(loads):  # the LISP conses the loads, so it sums them last run first
			if load is not None:
				total = total + load
		factor = _j(driver, "usable_load_factor")
		usable = rated * (factor if _number(factor) else 1.0)
		if total > usable:
			issues.append(
				_issue(
					"PSU_OVERLOAD",
					psu.get("id"),
					"warning",
					f"{num_str(round_py(total, 2), 1)} W on {num_str(round_py(usable, 2), 1)} W usable; "
					"the System Designer will reassign outputs",
				)
			)
	return issues


# --- Controls (il-controls.lsp) ---------------------------------------------------------------


def _dmx(control):
	dmx = control.get("dmx")
	return dmx if isinstance(dmx, dict) else {}


def _universe(control):
	universe = _dmx(control).get("universe")
	return universe if universe is not None else 1


def _footprint(catalog, control):
	footprint = _j(cat_control(catalog, control.get("item_code")), "dmx_footprint")
	return footprint if _number(footprint) and footprint > 0 else 1


def dmx_patch(package, catalog):
	"""``il-dmx-patch``: ``[(universe, id, start, end, auto), ...]`` by universe, then start."""
	receivers = [
		control
		for control in _items(package.get("controls"))
		if _j(cat_control(catalog, control.get("item_code")), "receives_dmx") is True
	]
	receivers = sorted(receivers, key=lambda control: control.get("id"))
	universes = []
	for control in receivers:
		if _universe(control) not in universes:
			universes.append(_universe(control))
	rows = []
	for universe in sorted(universes):
		used, placed = [], []
		members = [control for control in receivers if _universe(control) == universe]
		for control in members:
			start = _dmx(control).get("start_address")
			if _number(start):
				end = start + _footprint(catalog, control) - 1
				used.insert(0, (start, end))
				placed.insert(0, (universe, control.get("id"), start, end, False))
		for control in members:
			if not _number(_dmx(control).get("start_address")):
				footprint, start = _footprint(catalog, control), 1
				while True:
					hits = [
						block for block in used if start <= block[1] and start + footprint - 1 >= block[0]
					]
					if not hits:
						break
					start = 1 + max(block[1] for block in hits)
				used.insert(0, (start, start + footprint - 1))
				placed.insert(0, (universe, control.get("id"), start, start + footprint - 1, True))
		rows.extend(sorted(placed, key=lambda row: row[2]))
	return rows


def _control_issues(package, catalog):
	issues = []
	controls = _items(package.get("controls"))
	for control in controls:
		if catalog is not None and cat_control(catalog, control.get("item_code")) is None:
			text = f"{_il_str(control.get('item_code'))} is not a control in the current catalog"
			issues.append(_issue("CONTROL_UNKNOWN", control.get("id"), "error", text))
	if catalog is not None:
		patch = dmx_patch(package, catalog)
		for universe, ref, start, end, _auto in patch:
			if end > DMX_CHANNELS:
				text = f"Needs channels {_itoa(start)}-{_itoa(end)} in universe {_itoa(universe)} (512 max)"
				issues.append(_issue("DMX_UNIVERSE_FULL", ref, "error", text))
			for other in patch:
				if universe == other[0] and ref < other[1] and start <= other[3] and end >= other[2]:
					text = f"{ref} and {other[1]} share channels in universe {_itoa(universe)}"
					issues.append(_issue("DMX_ADDRESS_OVERLAP", ref, "error", text))
	for zone in _items(package.get("zones")):
		link = zone.get("control") if isinstance(zone.get("control"), dict) else {}
		if link.get("id") is None:
			continue
		control = next((item for item in controls if item.get("id") == link["id"]), None)
		item = cat_control(catalog, control.get("item_code")) if control and catalog is not None else None
		if item is None:
			continue
		port = _first(_j(item, "ports"), "name", link.get("port"))
		protocol = _j(port, "protocol")
		wanted = ZONE_PROTOCOLS.get(zone.get("method"))
		if port is None:
			text = f"{link['id']} has no output {_il_str(link.get('port'))}"
			issues.append(_issue("PROTOCOL_MISMATCH", zone.get("id"), "error", text))
		elif wanted is not None and protocol != wanted:
			text = f"{zone.get('method')} zone on a {_il_str(protocol)} output of {link['id']}"
			issues.append(_issue("PROTOCOL_MISMATCH", zone.get("id"), "error", text))
	return issues


# --- Groups (il-check-groups, il-model.lsp) ---------------------------------------------------

GROUP_FAMILIES = ("Linear Fixture", *TAPE_FAMILIES)
MAX_GROUP_MEMBERS = 12


def _canonical(value):
	import json

	return json.dumps(value, sort_keys=True, separators=(",", ":"))


def group_issues(package):
	"""``il-check-groups``: issues on each group (ref: the group id), then on stacked runs in no group.

	Model rules only, no catalog: the drawing import runs them itself so they hold whether or not the
	catalog can be built. A group is one schedule line, so its runs share one style, Type and room.
	"""
	issues = []
	runs = {run.get("id"): run for run in _items(package.get("runs"))}
	seen = set()
	for group in _items(package.get("groups")):
		group_id = group.get("id")
		listed = _items(group.get("runs"))
		members = [runs[run_id] for run_id in listed if run_id in runs]
		for run_id in listed:
			if run_id not in runs:
				issues.append(
					_issue(
						"GROUP_UNKNOWN_RUN", group_id, "error", f"Run {_il_str(run_id)} is not in the drawing"
					)
				)
			elif run_id in seen:
				issues.append(
					_issue(
						"GROUP_RUN_IN_TWO_GROUPS",
						group_id,
						"error",
						f"Run {run_id} is already in another group",
					)
				)
			seen.add(run_id)
		if not members:
			issues.append(
				_issue("GROUP_EMPTY", group_id, "error", "The group has no runs; add runs with ILGROUP")
			)
			continue
		count = sum(int(run.get("copies") or 1) for run in members)
		if count > MAX_GROUP_MEMBERS:
			issues.append(
				_issue(
					"GROUP_TOO_MANY",
					group_id,
					"error",
					f"{count} runs, copies included; a group holds at most {MAX_GROUP_MEMBERS}",
				)
			)
		styles = {_canonical(run.get("style")) for run in members}
		if len(styles) > 1:
			issues.append(
				_issue(
					"GROUP_MIXED_STYLE",
					group_id,
					"error",
					"Runs in a group need one style; apply one with ILSTYLE",
				)
			)
		family = _j(members[0].get("style"), "family")
		if family not in GROUP_FAMILIES:
			issues.append(
				_issue("GROUP_FAMILY", group_id, "error", f"{_il_str(family)} runs cannot be grouped")
			)
		types = sorted(
			{_il_str(run.get("fixture_type")) for run in members} - {_il_str(group.get("fixture_type"))}
		)
		if types:
			issues.append(
				_issue(
					"GROUP_MIXED_TYPE",
					group_id,
					"error",
					f"Runs of Type {', '.join(types)} in a group of Type {_il_str(group.get('fixture_type'))}",
				)
			)
		rooms = {run.get("room") for run in members if run.get("room")}
		if group.get("room"):
			rooms.add(group["room"])
		if len(rooms) > 1:
			issues.append(
				_issue(
					"GROUP_MIXED_ROOM",
					group_id,
					"error",
					f"Runs in rooms {', '.join(sorted(rooms))}; a group is in one room",
				)
			)
		feeds = {(run.get("feed") or {}).get("method") or "end" for run in members}
		if len(feeds) > 1:
			issues.append(
				_issue(
					"GROUP_MIXED_FEED",
					group_id,
					"warning",
					f"Runs fed {', '.join(sorted(feeds))}; the System Designer uses one feed method for the group",
				)
			)
	for run in runs.values():
		if int(run.get("copies") or 1) > 1 and run.get("id") not in seen:
			issues.append(
				_issue(
					"COPIES_NOT_IN_GROUP",
					run.get("id"),
					"error",
					"A stacked run must be in a group; run ILUPDATE",
				)
			)
	return issues


# --- Public API -------------------------------------------------------------------------------


def check_package(package: dict, catalog: dict | None) -> list[dict]:
	"""Every ported ILCHECK issue in PACKAGE (``ilq/2``, defaults filled) against CATALOG (``cad-catalog/1``).

	Issues are ``{"code", "ref", "severity", "text"}`` in the LISP's order: runs, PSUs, controls, groups.
	Overrides are not applied; see :func:`apply_overrides`.
	"""
	issues = []
	if catalog is None:
		issues.append(
			_issue("CATALOG_MISSING", "drawing", "error", "Load the CAD catalog (ILCATALOG) before checking")
		)
	for run in _items(package.get("runs")):
		issues.extend(_run_issues(run, catalog))
	issues.extend(_psu_issues(package, catalog))
	issues.extend(_control_issues(package, catalog))
	issues.extend(group_issues(package))
	return issues


def overridden(issue, overrides) -> bool:
	"""``il-overridden-p``: an override with the issue's code and ref covers it."""
	return any(
		_j(override, "code") == issue.get("code") and _j(override, "ref") == issue.get("ref")
		for override in overrides or []
	)


def apply_overrides(issues, overrides) -> list:
	"""The issues no override covers (``package["check"]["overrides"]``), in order."""
	return [issue for issue in issues if not overridden(issue, overrides)]


def issue_counts(issues, overrides) -> tuple[int, int]:
	"""``il-issue-counts``: ``(errors, warnings)`` not covered by an override."""
	kept = apply_overrides(issues, overrides)
	return (
		sum(1 for issue in kept if issue.get("severity") == "error"),
		sum(1 for issue in kept if issue.get("severity") == "warning"),
	)
