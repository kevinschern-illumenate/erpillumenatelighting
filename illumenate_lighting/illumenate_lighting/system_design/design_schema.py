# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""The design document contract on the server (plan H5, WP-2.2).

``validate_design_json`` checks a design against the JSON Schema exported from the Zod
``DesignSchema`` (committed at ``public/system_designer/schema/design.schema.json``), then the
cross-reference rules JSON Schema cannot express, then the Settings VD ceiling. ``build_hash`` is
byte-for-byte the TypeScript ``buildHash``; both sides test against the same fixtures.
"""

import hashlib
import json
import math
from functools import cache
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "public/system_designer/schema/design.schema.json"
VD_LOOSENED = "VD_TARGET_LOOSENED"
# Design project setting -> System Designer Settings field (D5).
VD_LIMITS = {
	"vdTargetLowVoltagePct": "vd_target_class2_pct",
	"vdTargetLineVoltagePct": "vd_target_line_pct",
	"vdTargetLandscapePct": "vd_target_landscape_pct",
}


def round_number(value):
	"""Round like JavaScript ``Math.round(value * 1000) / 1000``; integral results become ints."""
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		return value
	if isinstance(value, float) and not math.isfinite(value):
		raise ValueError("Canonical JSON cannot hold NaN or Infinity")
	rounded = math.floor(value * 1000 + 0.5) / 1000
	return int(rounded) if float(rounded).is_integer() else rounded


def _canonical(value):
	if isinstance(value, dict):
		return {key: _canonical(value[key]) for key in sorted(value)}
	if isinstance(value, list):
		return [_canonical(item) for item in value]
	return round_number(value)


def canonical_json(value):
	return json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build_hash(design):
	"""SHA-256 of the canonical design without ``views``."""
	body = {key: value for key, value in design.items() if key != "views"}
	return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


@cache
def _validator():
	from jsonschema import Draft202012Validator

	schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
	return Draft202012Validator(schema)


def _path(parts):
	return "/".join(str(part) for part in parts) or "(root)"


def schema_problems(design):
	errors = sorted(_validator().iter_errors(design), key=lambda error: list(error.absolute_path))
	return [f"{_path(error.absolute_path)}: {error.message}" for error in errors[:20]]


def reference_problems(design):
	"""The Zod ``superRefine`` rules: unique run keys, runs and cabinets in known spaces."""
	problems = []
	site = design.get("site") or {}
	spaces = {space.get("id") for space in site.get("spaces") or []}
	seen = set()
	for index, run in enumerate(design.get("runs") or []):
		if run.get("key") in seen:
			problems.append(f"runs/{index}/key: Duplicate run key: {run.get('key')}")
		seen.add(run.get("key"))
		if run.get("spaceId") not in spaces:
			problems.append(f"runs/{index}/spaceId: Unknown space: {run.get('spaceId')}")
	for index, cabinet in enumerate(site.get("cabinets") or []):
		if cabinet.get("spaceId") not in spaces:
			problems.append(f"site/cabinets/{index}/spaceId: Unknown space: {cabinet.get('spaceId')}")
	return problems


def vd_problems(design, settings):
	"""Project VD targets may be tighter than Settings, never looser without a staff override (D5)."""
	if any(
		item.get("code") == VD_LOOSENED and item.get("kind") == "staff-override"
		for item in design.get("overrides") or []
	):
		return []
	project_settings = (design.get("project") or {}).get("settings") or {}
	problems = []
	for key, field in VD_LIMITS.items():
		value, limit = project_settings.get(key), settings.get(field)
		if isinstance(value, (int, float)) and limit is not None and value > float(limit):
			problems.append(f"project/settings/{key}: {value}% is looser than the {float(limit)}% limit")
	return problems


def validate_design_json(design, settings=None):
	"""Return a list of problems (empty when valid). ``settings`` is the System Designer Settings."""
	if not isinstance(design, dict):
		return ["(root): a design must be a JSON object"]
	problems = schema_problems(design)
	if problems:
		return problems
	problems = reference_problems(design)
	if settings is not None:
		problems += vd_problems(design, settings)
	return problems
