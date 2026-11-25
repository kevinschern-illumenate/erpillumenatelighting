"""The ILCHECK rules on the server (WP 1.9) against the shared cases, and against the AutoLISP itself.

``system_design/drawing_checks.py`` must give the issues ``tools/system_designer/fixtures/cad/check-cases.json``
expects, and the same (code, ref, severity, text) as the toolkit's ``il-check`` run by the mini interpreter
on the same drawing: each case's package is turned into a LISP model (runs drawn as polylines whose lit
pieces have the segments' lengths and arc radii), checked by the LISP, and written back out by the LISP's
own ``il-package`` writer, which the Python must check the same way.
"""

import copy
import json
import math
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from illumenate_lighting.illumenate_lighting.system_design import drawing_checks, ilq_schema
from tools.cad_toolkit.test import mini_lisp
from tools.cad_toolkit.test.mini_lisp import alist, from_python_json, lst, to_alist, to_python_json

LISP = REPO / "tools/cad_toolkit/lisp"
FIXTURES = REPO / "tools/system_designer/fixtures/cad"
PURE = (
	"il-util.lsp",
	"il-json.lsp",
	"il-math.lsp",
	"il-sha256.lsp",
	"il-catalog.lsp",
	"il-model.lsp",
	"il-controls.lsp",
)
CASES = json.loads((FIXTURES / "check-cases.json").read_text(encoding="utf-8"))["cases"]
SAMPLE = json.loads((FIXTURES / "catalog.sample.json").read_text(encoding="utf-8"))
TODAY = "2026-11-25"


def merge(base, patch):
	"""The fixture's ``catalog_patch``: objects merge by key, list items by id, else code, else append."""
	if isinstance(base, dict) and isinstance(patch, dict):
		merged = dict(base)
		for key, value in patch.items():
			merged[key] = merge(base[key], value) if key in base else copy.deepcopy(value)
		return merged
	if isinstance(base, list) and isinstance(patch, list):
		merged = list(base)
		for item in patch:
			key = next((name for name in ("id", "code") if isinstance(item, dict) and name in item), None)
			index = next(
				(
					i
					for i, old in enumerate(merged)
					if key and isinstance(old, dict) and old.get(key) == item[key]
				),
				None,
			)
			if index is None:
				merged.append(copy.deepcopy(item))
			else:
				merged[index] = merge(merged[index], item)
		return merged
	return copy.deepcopy(patch)


def case_catalog(case):
	return None if case.get("no_catalog") else merge(SAMPLE, case.get("catalog_patch") or {})


def case_package(case):
	"""The case's package parts filled into a whole ``ilq/2`` package, with the import's defaults."""
	parts = copy.deepcopy(case["package"])
	package = {
		"schema": "ilq/2",
		"toolkit": {"version": "0.4.5", "platform": "AutoCAD 2025"},
		"catalog": {"snapshot_hash": SAMPLE["snapshot_hash"], "generated_at": SAMPLE["generated_at"]},
		"drawing": {
			"file": "case.dwg",
			"rev": 0,
			"hash": "sha256:" + "a" * 64,
			"units": "in",
			"scale_verified": True,
		},
		"runs": [],
		"check": {"errors": 0, "warnings": 0, **parts.pop("check", {})},
		**parts,
	}
	for index, run in enumerate(package["runs"]):
		run.setdefault("handle", format(0x100 + index, "X"))
		run.setdefault("fixture_type", run["id"].split("-")[0])
	for index, control in enumerate(package.get("controls") or []):
		control.setdefault("handle", format(0x800 + index, "X"))
	for index, group in enumerate(package.get("groups") or []):
		group.setdefault("handle", format(0x900 + index, "X"))
		group.setdefault("fixture_type", "T1")
	return ilq_schema.with_defaults(package)


def keyed(issues):
	return sorted((issue["code"], issue["ref"], issue["severity"]) for issue in issues)


def full(issues):
	return sorted((issue["code"], issue["ref"], issue["severity"], issue["text"]) for issue in issues)


# --- The same drawing as a LISP model -----------------------------------------------------------


def polyline(segments):
	"""(vertices, breaks, spans) whose lit pieces are SEGMENTS: an arc of the segment's radius, then
	straight; pieces joined by jumper breaks. No segments: one span, all jumper (RUN_NO_TAPE)."""
	if not segments:
		return [[0.0, 0.0, 0.0], [12.0, 0.0, 0.0]], [], [0]
	vertices, breaks, x = [[0.0, 0.0, 0.0]], [], 0.0
	for index, segment in enumerate(segments):
		if index:
			breaks.append(len(vertices) - 1)
		length, radius = float(segment["path_length_in"]), segment.get("min_arc_radius_in")
		if radius:
			sweep = min(math.pi / 2, length / radius)
			vertices[-1][2] = math.tan(sweep / 4)
			x += 2 * radius * math.sin(sweep / 2)
			vertices.append([x, 0.0, 0.0])
			length -= radius * sweep
		if length > 1e-9:
			x += length
			vertices.append([x, 0.0, 0.0])
	return vertices, breaks, []


def optional(values, source, *keys):
	for key in keys:
		if source.get(key) is not None:
			values[key] = source[key]
	return values


def lisp_model(package):
	styles, runs = [], []
	for index, run in enumerate(package["runs"]):
		styles.append(from_python_json({**run["style"], "id": f"style:{index}"}))
		vertices, breaks, spans = polyline(run["segments"])
		values = {
			"id": run["id"],
			"handle": run["handle"],
			"fixture_type": run["fixture_type"],
			"style": f"style:{index}",
			"vertices": lst(lst(vertex) for vertex in vertices),
			"breaks": lst(breaks),
			"spans": lst(spans),
			"jumper_in": 12.0,
			"feed_method": run["feed"]["method"],
		}
		if (run.get("copies") or 1) > 1:
			values["copies"] = run["copies"]
		runs.append(to_alist(optional(values, run, "room", "cabinet", "label")))
	controls = []
	for control in package["controls"]:
		values = {
			"id": control["id"],
			"handle": control["handle"],
			"item_code": control["item_code"],
			"start": "auto",
		}
		if control.get("dmx"):
			values.update(universe=control["dmx"]["universe"], start=control["dmx"]["start_address"])
		controls.append(to_alist(optional(values, control, "cabinet", "room", "control_from")))
	zones = []
	for zone in package["zones"]:
		values = {"id": zone["id"], "name": zone["name"], "method": zone["method"], "runs": lst(zone["runs"])}
		if zone.get("control"):
			values.update(control=zone["control"]["id"], port=zone["control"]["port"])
		zones.append(to_alist(values))
	groups = []
	for group in package.get("groups") or []:
		power = group.get("power") or {}
		values = {
			"id": group["id"],
			"handle": group["handle"],
			"fixture_type": group["fixture_type"],
			"runs": lst(group["runs"]),
			"include": "1" if power.get("include_supplies", True) else "0",
			"allocation": power.get("allocation") or "grouped",
		}
		if power.get("override_max_run_ft"):
			values["override"] = power["override_max_run_ft"]
		groups.append(to_alist(optional(values, group, "room", "location", "notes")))
	return to_alist(
		{
			"drawing": to_alist(
				{"file": "case.dwg", "rev": 0, "hash": "sha256:" + "a" * 64, "scale_verified": mini_lisp.T}
			),
			"rooms": lst(to_alist(room) for room in package["rooms"]),
			"cabinets": lst(to_alist(cabinet) for cabinet in package["cabinets"]),
			"runs": lst(runs),
			"styles": lst(styles),
			"psus": lst(
				to_alist(optional({"id": psu["id"], "runs": lst(psu["runs"])}, psu, "item_code", "cabinet"))
				for psu in package["psus"]
			),
			"wires": lst(
				to_alist(
					{
						"id": w["id"],
						"from": w["from"],
						"to": w["to"],
						"kind": w["kind"],
						"length_in": w["path_length_in"],
					}
				)
				for w in package["wire_paths"]
			),
			"controls": lst(controls),
			"zones": lst(zones),
			"groups": lst(groups),
			"overrides": lst(to_alist(override) for override in package["check"]["overrides"]),
		}
	)


def interpreter():
	interp = mini_lisp.Interpreter()
	for name in PURE:
		interp.load(LISP / name)
	return interp


def lisp_issue(value):
	issue = alist(value)
	return {key: issue[key] for key in ("code", "ref", "severity", "text")}


class Fixture(unittest.TestCase):
	def test_cases_give_the_expected_issues(self):
		for case in CASES:
			with self.subTest(case["name"]):
				package, catalog = case_package(case), case_catalog(case)
				if case.get("schema_valid", True):
					self.assertEqual(ilq_schema.validate_package(package), [])
				issues = drawing_checks.check_package(package, catalog)
				self.assertTrue({issue["code"] for issue in issues} <= drawing_checks.PORTED_CODES)
				self.assertEqual(keyed(issues), keyed(case["expected"]))
				for expected in case["expected"]:
					if "text" in expected:
						texts = [
							i["text"]
							for i in issues
							if (i["code"], i["ref"]) == (expected["code"], expected["ref"])
						]
						self.assertIn(expected["text"], texts)
				overrides = package["check"]["overrides"]
				if "expected_after_overrides" in case:
					kept = drawing_checks.apply_overrides(issues, overrides)
					self.assertEqual(keyed(kept), keyed(case["expected_after_overrides"]))
				if "expected_counts" in case:
					self.assertEqual(
						list(drawing_checks.issue_counts(issues, overrides)), case["expected_counts"]
					)
				if "expected_patch" in case:
					patch = drawing_checks.dmx_patch(package, catalog)
					self.assertEqual([list(row) for row in patch], case["expected_patch"])

	def test_every_ported_rule_has_a_positive_and_a_negative_case(self):
		for code in sorted(drawing_checks.PORTED_CODES):
			with self.subTest(code):
				listed = [case for case in CASES if code in case["rules"]]
				found = [case for case in listed if code in {issue["code"] for issue in case["expected"]}]
				self.assertTrue(found, f"no case expects {code}")
				self.assertTrue(len(found) < len(listed), f"no case where {code} must not fire")

	def test_overrides_need_the_same_code_and_ref(self):
		issues = [
			{"code": "BEND_RADIUS", "ref": "N1-01", "severity": "error", "text": ""},
			{"code": "PSU_OVERLOAD", "ref": "PS-01", "severity": "warning", "text": ""},
			{"code": "BEND_RADIUS", "ref": "N1-02", "severity": "info", "text": ""},
		]
		overrides = [
			{"code": "BEND_RADIUS", "ref": "N1-02", "note": "ok"},
			{"code": "PSU_OVERLOAD", "ref": "N1-01", "note": "x"},
		]
		self.assertEqual(drawing_checks.apply_overrides(issues, overrides), issues[:2])
		self.assertEqual(drawing_checks.apply_overrides(issues, None), issues)
		self.assertEqual(drawing_checks.issue_counts(issues, overrides), (1, 1))

	def test_number_text_and_rounding_match_the_lisp(self):
		lisp = interpreter()
		for value, digits in (
			(1.0, 2),
			(1.9685, 2),
			(0.4724, 3),
			(86.62, 1),
			(60.0, 1),
			(76.8, 1),
			(12, 1),
			(-0.00001, 2),
			(0.125, 2),
			(2.675, 2),
		):
			with self.subTest((value, digits)):
				self.assertEqual(
					drawing_checks.num_str(value, digits), lisp.call("il-num->str", value, digits)
				)
		for value, digits in (
			(118.11023622, 4),
			(43.307086, 2),
			(2.5, 0),
			(3.5, 0),
			(0.125, 2),
			(76.509186, 2),
			(1e-5, 4),
		):
			with self.subTest(("round", value, digits)):
				self.assertEqual(
					drawing_checks.round_py(value, digits), lisp.call("il-round-py", value, digits)
				)
		for length, cut, free in (
			(120.0, 50, False),
			(210.0, 50, False),
			(106.2, 50, False),
			(0.5, 50, False),
			(310.0, None, True),
			(24.0, 25, False),
		):
			with self.subTest(("snap", length, cut)):
				snapped = alist(lisp.call("il-cut-snap", length, cut, mini_lisp.T if free else None))[
					"mfg_in"
				]
				self.assertEqual(drawing_checks.cut_snap_in(length, cut, free), snapped)


class LispParity(unittest.TestCase):
	"""The LISP ``il-check`` on the same drawing reports the same issues for every ported code."""

	@classmethod
	def setUpClass(cls):
		cls.lisp = interpreter()

	def lisp_issues(self, model, catalog):
		issues = self.lisp.call("il-check", model, catalog, TODAY) or []
		return [lisp_issue(issue) for issue in issues if alist(issue)["code"] in drawing_checks.PORTED_CODES]

	def test_il_check_agrees_on_every_case(self):
		for case in CASES:
			with self.subTest(case["name"]):
				package, catalog = case_package(case), case_catalog(case)
				model, lisp_catalog = lisp_model(package), from_python_json(catalog)
				expected = self.lisp_issues(model, lisp_catalog)
				python = drawing_checks.check_package(package, catalog)
				self.assertEqual(full(python), full(expected))
				self.assertEqual([i["code"] for i in python], [i["code"] for i in expected], "same order")
				overrides = alist(model)["overrides"]
				kept = [i for i in expected if not self.lisp.call("il-overridden-p", to_alist(i), overrides)]
				self.assertEqual(
					full(drawing_checks.apply_overrides(python, package["check"]["overrides"])), full(kept)
				)
				if catalog is not None:
					patch = [
						[row[0], row[1], row[2], row[3], row[4] is mini_lisp.T]
						for row in self.lisp.call("il-dmx-patch", model, lisp_catalog) or []
					]
					self.assertEqual([list(row) for row in drawing_checks.dmx_patch(package, catalog)], patch)

	def test_the_package_the_lisp_writes_checks_the_same(self):
		for case in CASES:
			with self.subTest(case["name"]):
				package, catalog = case_package(case), case_catalog(case)
				model, lisp_catalog = lisp_model(package), from_python_json(catalog)
				issues = self.lisp.call("il-check", model, lisp_catalog, TODAY)
				written = to_python_json(
					self.lisp.call("il-package", model, lisp_catalog, issues, "AutoCAD 2025")
				)
				if catalog is None:
					written["catalog"] = package["catalog"]
				if case.get("schema_valid", True):
					self.assertEqual(ilq_schema.validate_package(written), [])
				python = drawing_checks.check_package(ilq_schema.with_defaults(written), catalog)
				self.assertEqual(full(python), full(self.lisp_issues(model, lisp_catalog)))


if __name__ == "__main__":
	unittest.main()
