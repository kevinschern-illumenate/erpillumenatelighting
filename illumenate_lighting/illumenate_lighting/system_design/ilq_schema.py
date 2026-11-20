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

	rooms, cabinets, runs, psus = unique("rooms"), unique("cabinets"), unique("runs"), unique("psus")
	unique("wire_paths")
	for index, cabinet in enumerate(package.get("cabinets") or []):
		if cabinet.get("room") and cabinet["room"] not in rooms:
			problems.append(f"cabinets/{index}/room: Unknown room: {cabinet['room']}")
	handles = set()
	for index, run in enumerate(package.get("runs") or []):
		if run.get("room") and run["room"] not in rooms:
			problems.append(f"runs/{index}/room: Unknown room: {run['room']}")
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
	ends = runs | psus | cabinets
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


def with_defaults(package):
	"""A copy with the Zod defaults filled in, so the import reads every key the same way."""
	package = copy.deepcopy(package)
	package.setdefault("target", {})
	package["target"].setdefault("schedule", "")
	package["target"].setdefault("schedule_version", 0)
	package["target"].setdefault("project", "")
	for section in ("rooms", "cabinets", "psus", "wire_paths", "other_lines"):
		package.setdefault(section, [])
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
