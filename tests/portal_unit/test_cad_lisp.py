"""The AutoCAD toolkit's pure AutoLISP (draw-to-quote plan 1.7, 3.10), run in CI by the mini interpreter.

The math must match the golden cases (and so the configurator), the JSON reader must read the CAD
catalog, and the package the LISP writes must pass the same ``ilq/2`` validator the portal import uses.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from test_services import ROOT, load_service

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.cad_toolkit.reference import cad_subset
from tools.cad_toolkit.test import mini_lisp
from tools.cad_toolkit.test.mini_lisp import (
	Sym,
	alist,
	from_python_json,
	lst,
	to_alist,
	to_python_json,
)

LISP = REPO / "tools/cad_toolkit/lisp"
FIXTURES = REPO / "tools/system_designer/fixtures/cad"
PURE = ("il-util.lsp", "il-json.lsp", "il-math.lsp", "il-sha256.lsp", "il-catalog.lsp", "il-model.lsp")
CASES = json.loads((FIXTURES / "lisp-subset.json").read_text(encoding="utf-8"))


def interpreter():
	interp = mini_lisp.Interpreter()
	for name in PURE:
		interp.load(LISP / name)
	return interp


def plain(value):
	"""LISP results as Python: alists become dicts, T/nil booleans where the reference has them."""
	if isinstance(value, list) and value and all(isinstance(item, mini_lisp.Pair) or (isinstance(item, list) and isinstance(item[0], str)) for item in value):
		return {key: plain(item) for key, item in alist(value).items()}
	if isinstance(value, list):
		return [plain(item) for item in value]
	if value is mini_lisp.T:
		return True
	return value


class GoldenMath(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.lisp = interpreter()

	def test_cut_snap(self):
		for case in CASES["cut_snap"]:
			with self.subTest(case):
				result = plain(self.lisp.call("il-cut-snap", float(case["length_in"]), case["cut_mm"], mini_lisp.T if case["free_cut"] else None))
				self.assertEqual(result, case["expected"])

	def test_run_split(self):
		for case in CASES["run_split"]:
			with self.subTest(case):
				result = plain(
					self.lisp.call(
						"il-run-split",
						float(case["length_in"]),
						case["w_per_ft"],
						case["cut_mm"],
						mini_lisp.T if case["free_cut"] else None,
						case["max_run_vd_ft"],
						case["override_ft"],
					)
				)
				expected = dict(case["expected"])
				self.assertEqual(result["runs_count"], expected["runs_count"])
				self.assertEqual(result["max_run_ft"], expected["max_run_ft"])
				self.assertEqual(result["pct_of_max"], expected["pct_of_max"])
				self.assertEqual(result["runs_in"], expected["runs_in"])

	def test_psu_load(self):
		for case in CASES["psu_load"]:
			with self.subTest(case):
				result = plain(self.lisp.call("il-psu-load", lst(case["loads_w"]), case["rated_w"], case["usable_load_factor"]))
				expected = dict(case["expected"])
				self.assertEqual(bool(result.get("over")), expected.pop("over"))
				result.pop("over", None)
				self.assertEqual(result, expected)

	def test_path_length(self):
		for case in CASES["path_length"]:
			with self.subTest(case):
				vertices = lst(lst(float(v) for v in vertex) for vertex in case["vertices"])
				result = plain(self.lisp.call("il-path-length", vertices, mini_lisp.T if case["closed"] else None))
				self.assertEqual(result, case["expected"])

	def test_split_vertices_at_jumpers(self):
		vertices = lst([lst([0.0, 0.0, 0.0]), lst([48.0, 0.0, 0.0]), lst([48.0, 30.0, 0.0])])
		segments = self.lisp.call("il-split-vertices", vertices, lst([1]))
		self.assertEqual(len(segments), 2)
		self.assertEqual(plain(segments[0]), [[0.0, 0.0, 0.0], [48.0, 0.0, 0.0]])
		self.assertEqual(plain(segments[1]), [[48.0, 0.0, 0.0], [48.0, 30.0, 0.0]])

	def test_number_text(self):
		self.assertEqual(self.lisp.call("il-num->str", 12.5, 4), "12.5")
		self.assertEqual(self.lisp.call("il-num->str", 12.0, 2), "12")
		self.assertEqual(self.lisp.call("il-num->str", -0.00001, 2), "0")
		self.assertEqual(self.lisp.call("il-round-even", 2.5), 2)
		self.assertEqual(self.lisp.call("il-round-even", 3.5), 4)


class Json(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.lisp = interpreter()

	def test_reads_the_cad_catalog_file(self):
		catalog = self.lisp.call("il-catalog-read", str(FIXTURES / "catalog.sample.json"))
		expected = json.loads((FIXTURES / "catalog.sample.json").read_text(encoding="utf-8"))
		self.assertEqual(to_python_json(catalog), expected)

	def test_round_trip_through_text_and_file(self):
		value = {"a": [1, 2.5, -3e-05, "x\"y\\z\n", True, False, None], "b": {"c": {}}, "d": []}
		text = self.lisp.call("il-json-text", from_python_json(value))
		self.assertEqual(json.loads(text), value)
		parsed = self.lisp.call("il-json-parse", text)
		self.assertEqual(to_python_json(parsed), value)
		with tempfile.TemporaryDirectory() as folder:
			path = str(Path(folder) / "out.json")
			big = {"rows": [{"id": f"R-{index:03d}", "w": index * 1.5} for index in range(300)]}
			self.lisp.call("il-json-write-file", from_python_json(big), path)
			self.assertEqual(json.loads(Path(path).read_text()), big)
			self.assertLess(max(len(line) for line in Path(path).read_text().splitlines()), 400)

	def test_bad_json_reports_an_error(self):
		self.assertIsNone(self.lisp.call("il-json-parse", '{"a": [1, 2'))
		self.assertTrue(self.lisp.get("*il-jr-error*"))

	def test_unicode_escapes_become_ascii(self):
		self.assertEqual(self.lisp.call("il-json-parse", '"0\\u201310 V \\u0041"'), "0?10 V A")


def run(run_id, vertices, style, room="Z-Kitchen", fixture_type="L1", **extra):
	values = {
		"id": run_id,
		"handle": format(abs(hash(run_id)) % 0xFFFF + 0x100, "X"),
		"fixture_type": fixture_type,
		"room": room,
		"location": "Kitchen",
		"style": style,
		"vertices": lst(lst(float(v) for v in vertex) for vertex in vertices),
		"feed_method": "end",
		"start_feed": "End",
		"lead_in": 60.0,
		"cabinet": "CAB-1",
	}
	values.update(extra)
	return to_alist(values)


class Model(unittest.TestCase):
	def setUp(self):
		self.lisp = interpreter()
		self.catalog = self.lisp.call("il-catalog-read", str(FIXTURES / "catalog.sample.json"))
		styles = [
			{"id": "preset:PRE-0001", "label": "HD 27K Dry", "family": "LED Tape", "template": "led-hd-sw", "selections": {"environment_rating": "Dry", "cct": "2700K", "output_level": "300 lm/ft"}},
			{"id": "custom:1", "family": "LED Neon", "template": "non-pnc-sw", "selections": {"cct": "2700K", "output_level": "200 lm/ft"}},
			{"id": "custom:kit", "family": "Extrusion Kit", "template": "KIT-AZ01", "selections": {"finish": "Silver"}, "tape": {"family": "LED Tape", "template": "led-hd-sw", "selections": {"environment_rating": "Wet", "cct": "2700K", "output_level": "300 lm/ft"}}},
			{"id": "custom:gone", "family": "LED Tape", "template": "led-xx-gone", "selections": {}},
		]
		self.runs = [
			run("L1-01", [[0, 0, 0], [96, 0, 0]], "preset:PRE-0001"),
			run("L1-02", [[0, 0, 0], [48.25, 0, 0], [48.25, 30, 0]], "preset:PRE-0001", breaks=lst([1]), jumper_in=12.0),
			run("L2-01", [[0, 0, 0], [499, 0, 0]], "preset:PRE-0001", fixture_type="L2"),
			run("L3-01", [[0, 0, 0.4142135623730951], [1, 1, 0]], "custom:1", fixture_type="L3"),
			run("L5-01", [[0, 0, 0.05], [78.75, 0, 0]], "custom:kit", fixture_type="L5"),
		]
		self.model = to_alist(
			{
				"drawing": to_alist({"file": "job.dwg", "rev": 2, "hash": "sha256:" + "c" * 64, "scale_verified": mini_lisp.T, "schedule": "SCH-1"}),
				"rooms": lst([to_alist({"id": "Z-Kitchen", "name": "Kitchen", "level": "L1", "env": "dry-concealed"})]),
				"cabinets": lst([to_alist({"id": "CAB-1", "room": "Z-Kitchen", "location_rating": "Dry"})]),
				"runs": lst(self.runs),
				"styles": lst(from_python_json(style) for style in styles),
				"psus": lst([to_alist({"id": "PS-01", "cabinet": "CAB-1", "item_code": "PS-96-24", "runs": lst(["L1-01", "L1-02", "L2-01"])})]),
				"wires": lst([to_alist({"id": "W-01", "from": "PS-01", "to": "L1-01", "kind": "lv", "length_in": 240.0})]),
				"others": lst([from_python_json({"fixture_type": "X1", "qty": 4, "manufacturer_name": "Acme Lighting", "watts_each": 12})]),
				"overrides": lst([to_alist({"code": "TAPE_RUN_TOO_LONG", "ref": "L2-01", "note": "Center feed on site"})]),
			}
		)

	def issues(self):
		return [plain(issue) for issue in self.lisp.call("il-check", self.model, self.catalog, "2026-11-25") or []]

	def test_hint_snaps_and_splits_like_the_configurator(self):
		style = self.lisp.call("il-model-style", self.model, "preset:PRE-0001")
		hint = plain(self.lisp.call("il-run-hint", self.runs[2], style, self.catalog))
		snapped = cad_subset.cut_snap(499, 50)["mfg_in"]
		split = cad_subset.run_split(snapped, 4.4, 50)
		self.assertEqual(hint["length_in"], 499.0)
		self.assertEqual(hint["snapped_in"], round(snapped, 2))
		self.assertEqual(hint["runs_count"], split["runs_count"])
		self.assertEqual(hint["max_run_ft"], split["max_run_ft"])
		self.assertEqual(hint["runs_in"], split["runs_in"])
		text = self.lisp.call("il-hint-text", self.lisp.call("il-run-hint", self.runs[0], style, self.catalog))
		self.assertEqual(text, "94.49 in  34.7 W  41% max")

	def test_check_finds_geometry_issues_and_counts_overrides(self):
		model = alist(self.model)
		model["runs"] = lst([*self.runs, run("L9-01", [[0, 0, 0], [10, 0, 0]], "custom:gone", fixture_type="L9", room=None, cabinet=None), run("L1-01", [[0, 0, 0], [1, 0, 0]], "preset:PRE-0001")])
		self.model = to_alist(model)
		issues = self.issues()
		codes = {(issue["code"], issue["ref"]) for issue in issues}
		self.assertIn(("TAPE_RUN_TOO_LONG", "L2-01"), codes)
		self.assertIn(("BEND_RADIUS", "L3-01"), codes)  # 1 in arc; the neon bends to 1.97 in
		self.assertIn(("TEMPLATE_DISCONTINUED", "L9-01"), codes)
		self.assertIn(("RUN_NO_ROOM", "L9-01"), codes)
		self.assertIn(("RUN_UNCONNECTED", "L9-01"), codes)
		self.assertIn(("RUN_DUPLICATE_ID", "L1-01"), codes)
		self.assertIn(("CUT_SNAP", "L1-01"), codes)
		self.assertIn(("PROFILE_NOT_CURVE_CAPABLE", "L5-01"), codes)
		self.assertNotIn(("TAPE_WIDER_THAN_PROFILE", "L5-01"), codes)  # 0.47 in tape in a 0.685 in channel
		errors, warnings = self.lisp.call("il-issue-counts", self.lisp.call("il-check", self.model, self.catalog, "2026-11-25"), alist(self.model)["overrides"])
		self.assertGreaterEqual(errors, 3)
		self.assertGreaterEqual(warnings, 1)

	def test_package_passes_the_portal_validator(self):
		issues = self.lisp.call("il-check", self.model, self.catalog, "2026-11-25")
		package = to_python_json(self.lisp.call("il-package", self.model, self.catalog, issues, "AutoCAD 2025"))
		text = self.lisp.call("il-json-text", self.lisp.call("il-package", self.model, self.catalog, issues, "AutoCAD 2025"))
		self.assertEqual(json.loads(text), package)
		with load_service(ROOT + ".system_design.ilq_schema") as (module, _frappe):
			self.assertEqual(module.validate_package(package), [])
		self.assertEqual(package["schema"], "ilq/2")
		self.assertEqual(package["catalog"]["snapshot_hash"], "0" * 63 + "1")
		jumpered = next(item for item in package["runs"] if item["id"] == "L1-02")
		self.assertEqual([segment["end_type"] for segment in jumpered["segments"]], ["JUMPER", "ENDCAP"])
		self.assertEqual(jumpered["segments"][0]["jumper_length_in"], 12.0)
		self.assertEqual(jumpered["segments"][0]["lead_length_in"], 60.0)
		self.assertEqual(jumpered["style"]["preset"], "HD 27K Dry")
		kit = next(item for item in package["runs"] if item["id"] == "L5-01")
		self.assertEqual(kit["style"]["tape"]["template"], "led-hd-sw")
		arc = next(item for item in package["runs"] if item["id"] == "L3-01")
		self.assertAlmostEqual(arc["segments"][0]["min_arc_radius_in"], 1.0, places=3)
		self.assertEqual(package["check"]["overrides"][0]["code"], "TAPE_RUN_TOO_LONG")
		self.assertEqual(package["other_lines"][0]["manufacturer_name"], "Acme Lighting")
		self.assertNotIn("price", text.lower())

	def test_receipt_stamps_erp_keys(self):
		receipt = from_python_json(
			{"schema": "ilq-receipt/1", "runs": [{"id": "L1-01", "line_key": "LK1", "configured_name": "CTN-1", "config_hash": "abc", "part_number": "PN-1", "server_length_in": 94.49}]}
		)
		index = self.lisp.call("il-receipt-index", receipt)
		stamped = alist(self.lisp.call("il-run-with-receipt", self.runs[0], index))
		self.assertEqual((stamped["line_key"], stamped["part_number"], stamped["server_in"]), ("LK1", "PN-1", 94.49))
		untouched = alist(self.lisp.call("il-run-with-receipt", self.runs[1], index))
		self.assertNotIn("line_key", untouched)

	def test_stale_catalog_warning(self):
		self.assertIsNone(self.lisp.call("il-catalog-stale", self.catalog, "2026-12-01"))
		self.assertIn("days old", self.lisp.call("il-catalog-stale", self.catalog, "2027-01-15"))


class AccoreconsoleRunner(unittest.TestCase):
	"""The runner AutoCAD runs (plan 3.10) passes here too, so a red AutoCAD report means AutoCAD differs."""

	def test_runner_passes_every_golden_case(self):
		lisp = interpreter()
		lisp.load(REPO / "tools/cad_toolkit/test/il-tests.lsp")
		with tempfile.TemporaryDirectory() as folder:
			report = Path(folder) / "report.txt"
			passed, failed = lisp.call("il-run-golden", str(FIXTURES / "lisp-subset.json"), str(report))
			self.assertEqual(failed, 0, report.read_text())
			self.assertEqual(passed, sum(len(CASES[group]) for group in ("cut_snap", "run_split", "psu_load", "path_length")))

	def test_runner_reports_a_wrong_case(self):
		lisp = interpreter()
		lisp.load(REPO / "tools/cad_toolkit/test/il-tests.lsp")
		cases = json.loads(json.dumps(CASES))
		cases["cut_snap"][0]["expected"]["mfg_in"] = 1.0
		with tempfile.TemporaryDirectory() as folder:
			path = Path(folder) / "cases.json"
			path.write_text(json.dumps(cases))
			_passed, failed = lisp.call("il-run-golden", str(path), str(Path(folder) / "report.txt"))
			self.assertEqual(failed, 1)
			self.assertIn("FAIL cut_snap 1", (Path(folder) / "report.txt").read_text())


class Sha256(unittest.TestCase):
	def test_matches_hashlib(self):
		import hashlib

		lisp = interpreter()
		for text in ("", "abc", "a" * 55, "a" * 56, "a" * 64, '{"runs":[{"id":"L1-01"}]}' * 7):
			with self.subTest(len(text)):
				self.assertEqual(lisp.call("il-sha256", text), hashlib.sha256(text.encode()).hexdigest())


# AutoLISP functions the toolkit may call (core AutoLISP plus non-ActiveX vl- functions available on
# full AutoCAD, LT 2024+ and Mac). A call to anything else is a typo or a platform risk.
AUTOLISP = set(
	"""
	+ - * / = /= < > <= >= 1+ 1- ~ abs and append apply ascii assoc atan atof atoi boole boundp car cdr caar cadr cdar cddr
	caddr cadddr cddddr chr close command cond cons cos defun dictadd dictremove dictsearch distance entdel entget entlast
	entmake entmakex entmod entnext entsel entupd equal eq exit expt findfile fix float foreach getdist getenv getfiled
	getint getkword getpoint getreal getstring getvar if initget itoa lambda last length list listp logand logior lsh
	mapcar max member min minusp namedobjdict not nth null numberp open or princ progn quote read-line regapp rem repeat
	reverse rtos setenv setq setvar sin sqrt ssget sslength ssname strcase strcat strlen subst substr tblsearch type
	vl-catch-all-apply vl-catch-all-error-message vl-catch-all-error-p vl-filename-base vl-position vl-princ-to-string
	vl-remove vl-remove-if vl-remove-if-not vl-some vl-sort vl-string-right-trim vl-string-search vl-string-trim while
	write-line zerop function
	""".split()
)
SPECIAL = {"quote", "function", "setq", "if", "cond", "while", "repeat", "foreach", "progn", "and", "or", "defun", "lambda"}


def calls_and_locals(forms):
	defined, calls, bindings = set(), set(), []

	def walk(form, quoted=False):
		if not isinstance(form, list) or quoted:
			return
		head = form[0]
		if isinstance(head, Sym):
			name = head.name.lower()
			if name == "quote":
				return
			if name == "defun":
				defined.add(form[1].name.lower())
				bindings.extend(item.name.lower() for item in (form[2] or []) if item is not Sym("/"))
				for item in form[3:]:
					walk(item)
				return
			if name == "lambda":
				bindings.extend(item.name.lower() for item in (form[1] or []) if item is not Sym("/"))
				for item in form[2:]:
					walk(item)
				return
			if name == "cond":
				for clause in form[1:]:
					for item in clause or []:
						walk(item)
				return
			if name == "foreach":
				bindings.append(form[1].name.lower())
				for item in form[2:]:
					walk(item)
				return
			if name not in ("t",):
				calls.add(name)
		for item in form[1:] if isinstance(head, Sym) else form:
			walk(item)

	for form in forms:
		walk(form)
	return defined, calls, bindings


class Sources(unittest.TestCase):
	def test_calls_are_defined_or_autolisp_and_locals_never_shadow_functions(self):
		forms = []
		for path in [*sorted(LISP.glob("*.lsp")), REPO / "tools/cad_toolkit/test/il-tests.lsp"]:
			forms.extend(mini_lisp.read_all(path.read_text(encoding="utf-8")))
		defined, calls, bindings = calls_and_locals(forms)
		unknown = sorted(calls - defined - AUTOLISP - SPECIAL)
		self.assertEqual(unknown, [], "calls to functions that are neither AutoLISP nor defined in the toolkit")
		shadowing = sorted(set(bindings) & (AUTOLISP | defined | {"angle", "set", "read", "load", "type"}))
		self.assertEqual(shadowing, [], "AutoLISP variables share the function namespace")

	def test_every_toolkit_file_parses_and_avoids_activex_in_the_core(self):
		for path in sorted(LISP.glob("*.lsp")):
			with self.subTest(path.name):
				text = path.read_text(encoding="utf-8")
				mini_lisp.read_all(text)
				self.assertTrue(all(ord(char) < 128 for char in text), "LISP files are ASCII")
				code = "\n".join(line.split(";", 1)[0] for line in text.lower().splitlines())
				if path.name != "il-extras.lsp":
					for word in ("(vlax-", "(vla-", "(vlr-"):
						self.assertNotIn(word, code, f"{word} is not available on LT 2024 or Mac")


if __name__ == "__main__":
	unittest.main()
