# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""The ``ilq/2`` draw-to-quote package on the server (CAD toolkit plan 1.5).

``validate_package`` checks a package against the JSON Schema exported from the Zod ``IlqPackageSchema``
(committed at ``public/system_designer/schema/ilq.schema.json``), then the cross-reference rules JSON
Schema cannot express (the Zod ``superRefine``). ``parse_package`` adds the size limit and fills the
defaults the AutoLISP writer may leave out. Both sides test against ``tools/system_designer/fixtures/cad``.
"""

import copy
import json
from functools import cache
from pathlib import Path

SCHEMA = "ilq/2"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "public/system_designer/schema/ilq.schema.json"
MAX_BYTES = 5 * 1024 * 1024
MAX_RUNS = 1000


class PackageError(ValueError):
	"""The package is not a valid ``ilq/2`` document; ``problems`` lists each path and reason."""

	def __init__(self, problems):
		super().__init__("; ".join(problems[:5]))
		self.problems = problems


@cache
def _validator():
	from jsonschema import Draft202012Validator

	return Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def _path(parts):
	return "/".join(str(part) for part in parts) or "(root)"


def schema_problems(package):
	errors = sorted(_validator().iter_errors(package), key=lambda error: list(error.absolute_path))
	return [f"{_path(error.absolute_path)}: {error.message}" for error in errors[:20]]


def reference_problems(package):
	"""Unique ids, known rooms/cabinets/runs, one handle per run, kits with their tape."""
	problems = []

	def unique(section):
		seen = set()
		for index, item in enumerate(package.get(section) or []):
			if item.get("id") in seen:
				problems.append(f"{section}/{index}/id: Duplicate id: {item.get('id')}")
			seen.add(item.get("id"))
		return seen

	sheets = unique("sheets")
	rooms, cabinets, runs, psus = unique("rooms"), unique("cabinets"), unique("runs"), unique("psus")
	unique("wire_paths")
	used_sheets = set()

	def known_sheet(sheet, path):
		if not sheet:
			return
		used_sheets.add(sheet)
		if sheet not in sheets:
			problems.append(f"{path}: Unknown sheet: {sheet}")

	for index, room in enumerate(package.get("rooms") or []):
		known_sheet(room.get("sheet"), f"rooms/{index}/sheet")
	for index, cabinet in enumerate(package.get("cabinets") or []):
		if cabinet.get("room") and cabinet["room"] not in rooms:
			problems.append(f"cabinets/{index}/room: Unknown room: {cabinet['room']}")
	handles = set()
	for index, run in enumerate(package.get("runs") or []):
		if run.get("room") and run["room"] not in rooms:
			problems.append(f"runs/{index}/room: Unknown room: {run['room']}")
		known_sheet(run.get("sheet"), f"runs/{index}/sheet")
		if run.get("cabinet") and run["cabinet"] not in cabinets:
			problems.append(f"runs/{index}/cabinet: Unknown cabinet: {run['cabinet']}")
		handle = str(run.get("handle") or "").upper()
		if handle in handles:
			problems.append(f"runs/{index}/handle: Duplicate handle: {run.get('handle')}")
		handles.add(handle)
		style = run.get("style") or {}
		if style.get("family") == "Extrusion Kit" and not style.get("tape"):
			problems.append(f"runs/{index}/style/tape: A kit style needs its tape")
	for index, psu in enumerate(package.get("psus") or []):
		if psu.get("cabinet") and psu["cabinet"] not in cabinets:
			problems.append(f"psus/{index}/cabinet: Unknown cabinet: {psu['cabinet']}")
		for position, run in enumerate(psu.get("runs") or []):
			if run not in runs:
				problems.append(f"psus/{index}/runs/{position}: Unknown run: {run}")
	controls = unique("controls")
	unique("zones")
	for control_id in controls & (runs | psus | cabinets):
		problems.append(f"controls: Control id is used elsewhere: {control_id}")
	for index, control in enumerate(package.get("controls") or []):
		if control.get("cabinet") and control["cabinet"] not in cabinets:
			problems.append(f"controls/{index}/cabinet: Unknown cabinet: {control['cabinet']}")
		if control.get("room") and control["room"] not in rooms:
			problems.append(f"controls/{index}/room: Unknown room: {control['room']}")
		source = control.get("control_from")
		if source and (source not in controls or source == control.get("id")):
			problems.append(f"controls/{index}/control_from: Unknown control: {source}")
		handle = str(control.get("handle") or "").upper()
		if handle in handles:
			problems.append(f"controls/{index}/handle: Duplicate handle: {control.get('handle')}")
		handles.add(handle)
	zoned = set()
	for index, zone in enumerate(package.get("zones") or []):
		if zone.get("control") and zone["control"].get("id") not in controls:
			problems.append(f"zones/{index}/control/id: Unknown control: {zone['control'].get('id')}")
		for position, run in enumerate(zone.get("runs") or []):
			if run not in runs:
				problems.append(f"zones/{index}/runs/{position}: Unknown run: {run}")
			elif run in zoned:
				problems.append(f"zones/{index}/runs/{position}: Run is in two zones: {run}")
			zoned.add(run)
	for index, count in enumerate(package.get("counts") or []):
		known_sheet(count.get("sheet"), f"counts/{index}/sheet")
		if count.get("room") and count["room"] not in rooms:
			problems.append(f"counts/{index}/room: Unknown room: {count['room']}")
	if (package.get("drawing") or {}).get("scale_verified"):
		for index, sheet in enumerate(package.get("sheets") or []):
			status = (sheet.get("scale") or {}).get("status")
			if sheet.get("id") in used_sheets and status != "verified":
				problems.append(
					f"sheets/{index}/scale/status: Drawing says its scale is verified "
					f"but sheet {sheet.get('id')} is {status}"
				)
	ends = runs | psus | cabinets | controls
	for index, wire in enumerate(package.get("wire_paths") or []):
		for end in ("from", "to"):
			if wire.get(end) not in ends:
				problems.append(f"wire_paths/{index}/{end}: Unknown end: {wire.get(end)}")
	return problems


def validate_package(package):
	"""A list of problems (empty when valid)."""
	if not isinstance(package, dict):
		return ["(root): a package must be a JSON object"]
	problems = schema_problems(package)
	return problems or reference_problems(package)


def derived_source(package):
	"""The ``source`` a package without one came from: DXF uploads say ``dxf-1``, the rest are AutoCAD."""
	toolkit = package.get("toolkit") or {}
	if toolkit.get("version") == "dxf-1":
		return {"tool": "dxf", "version": "dxf-1", "platform": toolkit.get("platform"), "input": "dxf"}
	return {
		"tool": "autocad",
		"version": toolkit.get("version") or "",
		"platform": toolkit.get("platform"),
		"input": "ilq",
	}


def with_defaults(package):
	"""A copy with the Zod defaults filled in, so the import reads every key the same way."""
	package = copy.deepcopy(package)
	package.setdefault("target", {})
	package["target"].setdefault("schedule", "")
	package["target"].setdefault("schedule_version", 0)
	package["target"].setdefault("project", "")
	for section in (
		"rooms",
		"cabinets",
		"psus",
		"wire_paths",
		"other_lines",
		"controls",
		"zones",
		"sheets",
		"counts",
	):
		package.setdefault(section, [])
	package.setdefault("source", derived_source(package))
	for sheet in package["sheets"]:
		sheet.setdefault("label", "")
	for control in package["controls"]:
		control.setdefault("erp", {})
		if control.get("dmx"):
			control["dmx"].setdefault("start_address", "auto")
	for zone in package["zones"]:
		zone.setdefault("runs", [])
	for room in package["rooms"]:
		room.setdefault("level", "")
		room.setdefault("env", "dry-concealed")
	for cabinet in package["cabinets"]:
		cabinet.setdefault("location_rating", "Dry")
		cabinet.setdefault("access_note", "")
	for psu in package["psus"]:
		psu.setdefault("runs", [])
	package["check"].setdefault("overrides", [])
	for run in package["runs"]:
		run["style"].setdefault("selections", {})
		if run["style"].get("tape"):
			run["style"]["tape"].setdefault("selections", {})
		run.setdefault("feed", {})
		run["feed"].setdefault("method", "end")
		run["feed"].setdefault("point_handles", [])
		run.setdefault("erp", {})
		for segment in run["segments"]:
			segment.setdefault("end_type", "ENDCAP")
	return package


def parse_package(content):
	"""Parse ``content`` (text, bytes or a dict), check it, and return it with defaults filled in."""
	if isinstance(content, (bytes, bytearray)):
		if len(content) > MAX_BYTES:
			raise PackageError(["(root): the package is larger than 5 MB"])
		content = content.decode("utf-8-sig")
	if isinstance(content, str):
		if len(content.encode("utf-8")) > MAX_BYTES:
			raise PackageError(["(root): the package is larger than 5 MB"])
		try:
			content = json.loads(content)
		except ValueError:
			raise PackageError(["(root): the package is not valid JSON"]) from None
	problems = validate_package(content)
	if problems:
		raise PackageError(problems)
	return with_defaults(content)
