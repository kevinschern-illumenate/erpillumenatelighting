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

from tools.cad_toolkit import package_bundle
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
PURE = ("il-util.lsp", "il-json.lsp", "il-math.lsp", "il-sha256.lsp", "il-catalog.lsp", "il-model.lsp", "il-controls.lsp")
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


class Copies(unittest.TestCase):
	"""Pure parts of ILUPDATE's copy handling and ILSETUP's rescale."""

	@classmethod
	def setUpClass(cls):
		cls.lisp = interpreter()

	def copies(self, *records):
		result = self.lisp.call("il-copies", lst(lst(record) for record in records))
		return [(pair.car, pair.cdr) for pair in result or []]

	def test_copies_keep_the_oldest_and_renumber_the_rest(self):
		self.assertEqual(self.copies(["a", "L1-01", None, "1A"], ["b", "L1-01", None, "2B"], ["c", "L1-02", None, "2C"]), [("b", "1A")])

	def test_the_entity_on_its_own_handle_keeps_the_id(self):
		# "a" was pasted from another drawing (new, smaller handle, stale self); "b" is the tagged original.
		self.assertEqual(self.copies(["a", "L1-01", "9F", "1A"], ["b", "L1-01", "2B", "2B"]), [("a", "2B")])

	def test_handles_compare_as_hex_numbers(self):
		self.assertEqual(self.copies(["a", "L1-01", None, "FF"], ["b", "L1-01", None, "100"]), [("b", "FF")])

	def test_unique_and_missing_ids_are_not_copies(self):
		self.assertEqual(self.copies(["a", "L1-01", None, "1A"], ["b", None, None, "1B"], ["c", "", None, "1C"]), [])

	def test_id_prefix(self):
		for given, expected in (("L1-03", "L1-"), ("CAB-2", "CAB-"), ("kitchen", "kitchen-"), ("W-10", "W-")):
			self.assertEqual(self.lisp.call("il-id-prefix", given), expected)

	def test_scale_about(self):
		self.assertEqual(self.lisp.call("il-scale-about", lst([10.0, 10.0, 0.0]), lst([20.0, 30.0, 0.0]), 0.5), [15.0, 20.0, 0.0])


class Ename:
	def __init__(self, drawing, handle):
		self.drawing, self.handle = drawing, handle

	def __repr__(self):
		return f"<Entity name: {self.handle}>"


class FakeDrawing:
	"""Just enough of AutoCAD's entity API (entget, entmod, ssget _X, handent, entnext) to run the
	toolkit's ILUPDATE copy pass and ILSETUP rescale against entities built in Python."""

	def __init__(self, interp):
		self.order, self.groups, self.xdata = [], {}, {}
		for name, function in {
			"entget": self.entget, "entmod": self.entmod, "entupd": lambda ename: ename, "regapp": lambda name: name,
			"ssget": self.ssget, "sslength": len, "ssname": lambda ss, index: ss[index], "handent": self.handent,
			"entnext": self.entnext, "getvar": lambda name: None, "entmake": self.entmake, "entlast": self.entlast,
			"tblsearch": lambda table, name: mini_lisp.T,
		}.items():
			interp.set(name, function)

	def add(self, kind, handle, groups, xdata=None):
		ename = Ename(self, handle)
		self.order.append(ename)
		self.groups[ename] = [(0, kind), *groups]
		self.xdata[ename] = dict(xdata or {})
		return ename

	def polyline(self, handle, points, xdata):
		return self.add("LWPOLYLINE", handle, [(70, 1), *((10, (x, y)) for x, y in points)], xdata)

	def insert(self, handle, block, point, scale, xdata=None, attributes=()):
		ename = self.add("INSERT", handle, [(2, block), (10, point), (41, scale), (42, scale), (43, scale)], xdata)
		for offset, (tag, value, position, height) in enumerate(attributes, 1):
			self.add("ATTRIB", f"{handle}{offset}", [(2, tag), (1, value), (10, position), (40, height)])
		return ename

	def entmake(self, data):
		groups = [(mini_lisp.car(g), tuple(g[1:]) if isinstance(g, list) else g.cdr) for g in data]
		kind = dict(groups)[0]
		if kind != "SEQEND":
			self.add(kind, f"F{len(self.order):03X}", [g for g in groups if g[0] != 0])
		return data

	def entlast(self):
		return next(e for e in reversed(self.order) if self.value(e, 0) != "ATTRIB")

	def handent(self, handle):
		return next((ename for ename in self.order if ename.handle == handle), None)

	def entnext(self, ename):
		index = self.order.index(ename) + 1
		return self.order[index] if index < len(self.order) else None

	def entget(self, ename, apps=None):
		data = [mini_lisp.Pair(-1, ename), mini_lisp.Pair(5, ename.handle)]
		for code, value in self.groups[ename]:
			data.append([code, *value] if isinstance(value, tuple) else mini_lisp.Pair(code, value))
		if apps and self.xdata[ename]:
			items = ["ILLUMENATE"]
			for key, value in self.xdata[ename].items():
				items += [mini_lisp.Pair(1000, key), mini_lisp.Pair(1000, value)]
			data.append([-3, items])
		return data

	def entmod(self, data):
		ename, groups = None, []
		for group in data:
			code = mini_lisp.car(group)
			if code == -1:
				ename = mini_lisp.cdr(group)
			elif code == -3:
				values = [mini_lisp.cdr(item) for item in group[1][1:]]
				self.xdata[ename] = dict(zip(values[::2], values[1::2], strict=True))
			elif code != 5:
				groups.append((code, tuple(group[1:]) if isinstance(group, list) else group.cdr))
		self.groups[ename] = groups
		return data

	def value(self, ename, code):
		return dict(self.groups[ename]).get(code)

	def attribute(self, insert, tag):
		ename = self.entnext(insert)
		while ename and self.value(ename, 0) == "ATTRIB":
			if self.value(ename, 2) == tag:
				return ename
			ename = self.entnext(ename)
		return None

	def ssget(self, mode, filters=None):
		import fnmatch

		found = []
		for ename in self.order:
			keep = True
			for item in filters or []:
				code = mini_lisp.car(item)
				if code == -3:
					keep = keep and bool(self.xdata[ename])
				elif code in (0, 2):
					keep = keep and fnmatch.fnmatchcase(str(self.value(ename, code) or ""), mini_lisp.cdr(item))
			if keep:
				found.append(ename)
		return found or None


class CopiedEntities(unittest.TestCase):
	"""ILUPDATE's copy pass and ILSETUP's rescale, run through the toolkit's own AutoCAD-side code."""

	def setUp(self):
		self.lisp = mini_lisp.Interpreter()
		self.drawing = FakeDrawing(self.lisp)
		text = package_bundle.joined_lisp()
		self.lisp.run(text.replace('(princ (strcat "\\nilLumenate CAD toolkit " *il-version* " loaded. Type ILHELP."))', ""))

	def test_copies_get_new_ids_and_lose_portal_links(self):
		d = self.drawing
		run = {"kind": "RUN", "id": "L1-01", "type": "L1", "line_key": "row-7", "part_number": "ILL-TAPE-1"}
		original = d.polyline("1A", [(0, 0), (12, 0)], run)
		old_copy = d.polyline("2B", [(0, 20), (12, 20)], run)
		new_copy = d.polyline("2C", [(0, 40), (12, 40)], {**run, "self": "1A"})
		room = d.polyline("30", [(0, 0), (10, 0), (10, 10), (0, 10)], {"kind": "ROOM", "id": "kitchen", "self": "30"})
		d.insert("31", "IL-ROOMTAG", (5.0, 5.0, 0.0), 1.0, {"kind": "TAG", "owner": "30"}, [("ID", "kitchen", (5.0, 5.0, 0.0), 0.1)])
		room_copy = d.polyline("40", [(100, 0), (110, 0), (110, 10), (100, 10)], {"kind": "ROOM", "id": "kitchen", "self": "30"})
		tag_copy = d.insert("41", "IL-ROOMTAG", (105.0, 5.0, 0.0), 1.0, {"kind": "TAG", "owner": "30"}, [("ID", "kitchen", (105.0, 5.0, 0.0), 0.1)])
		psu = {"kind": "PSU", "id": "PS-01", "runs": "L1-01"}
		d.insert("50", "IL-PSUTAG", (0.0, 0.0, 0.0), 1.0, psu, [("TAG", "PS-01", (0.0, 0.0, 0.0), 0.1)])
		psu_copy = d.insert("60", "IL-PSUTAG", (50.0, 0.0, 0.0), 1.0, psu, [("TAG", "PS-01", (50.0, 0.0, 0.0), 0.1)])

		self.lisp.call("il-fix-copies", None)

		self.assertEqual(d.xdata[original]["id"], "L1-01")
		self.assertEqual(d.xdata[original]["line_key"], "row-7")
		self.assertEqual({d.xdata[old_copy]["id"], d.xdata[new_copy]["id"]}, {"L1-02", "L1-03"})
		for copy in (old_copy, new_copy):
			self.assertNotIn("line_key", d.xdata[copy])
			self.assertNotIn("part_number", d.xdata[copy])
		for ename in (original, old_copy, new_copy, room, room_copy):
			self.assertEqual(d.xdata[ename]["self"], ename.handle)
		self.assertEqual(d.xdata[room]["id"], "kitchen")
		self.assertEqual(d.xdata[room_copy]["id"], "kitchen-01")
		self.assertEqual(d.xdata[tag_copy]["owner"], "40")
		self.assertEqual(d.value(d.attribute(tag_copy, "ID"), 1), "kitchen-01")
		self.assertEqual(d.xdata[d.handent("31")]["owner"], "30")
		self.assertEqual(d.xdata[psu_copy]["id"], "PS-02")
		self.assertNotIn("runs", d.xdata[psu_copy])
		self.assertEqual(d.value(d.attribute(psu_copy, "TAG"), 1), "PS-02")

		# A second pass finds nothing left to fix.
		before = {ename: dict(d.xdata[ename]) for ename in d.order}
		self.lisp.call("il-fix-copies", None)
		self.assertEqual(before, {ename: dict(d.xdata[ename]) for ename in d.order})

	def test_tags_are_placed_centred(self):
		insert = self.lisp.call("il-insert", "IL-RUNTAG", lst([10.0, 10.0, 0.0]), 48.0, "E-ANNO-TAGS", None)
		d = self.drawing
		attribute = d.attribute(insert, "TAG")
		self.assertEqual(d.value(attribute, 72), 1)
		self.assertEqual(d.value(attribute, 74), 0)
		self.assertEqual(d.value(attribute, 11), (10.0, 7.744, 0.0))
		self.assertEqual(d.value(d.attribute(insert, "STYLE"), 11), (10.0, -2.0, 0.0))

	def test_title_block_fields_stay_left(self):
		insert = self.lisp.call("il-insert", "IL-TB-ARCH-D", lst([0.0, 0.0, 0.0]), 1.0, "E-ANNO-TTLB", None)
		attribute = self.drawing.attribute(insert, "PROJECT")
		self.assertEqual(self.drawing.value(attribute, 72), 0)
		self.assertIsNone(self.drawing.value(attribute, 11))

	def test_old_left_tags_are_recentred_once(self):
		d = self.drawing
		old = d.insert("1A", "IL-ROOMTAG", (100.0, 50.0, 0.0), 48.0, {"kind": "TAG"}, [("NAME", "Kitchen", (100.0, 50.0, 0.0), 6.0), ("ID", "kitchen", (100.0, 41.36, 0.0), 4.5)])
		d.groups[old].append((50, 0.0))
		title = d.insert("2A", "IL-TB-ARCH-D", (0.0, 0.0, 0.0), 1.0, None, [("PROJECT", "Job", (30.0, 20.0, 0.0), 0.125)])

		self.assertEqual(self.lisp.call("il-recenter-tags"), 2)
		name = d.attribute(old, "NAME")
		self.assertEqual((d.value(name, 72), d.value(name, 11)), (1, (100.0, 50.0, 0.0)))
		self.assertEqual(d.value(d.attribute(old, "ID"), 11), (100.0, 41.36, 0.0))
		self.assertIsNone(d.value(d.attribute(title, "PROJECT"), 72))
		self.assertEqual(self.lisp.call("il-recenter-tags"), 0)

	def test_rescale_resizes_symbols_but_not_title_blocks(self):
		d = self.drawing
		tag = d.insert("1A", "IL-RUNTAG", (10.0, 10.0, 0.0), 48.0, {"kind": "TAG"}, [("TAG", "L1-01", (-2.48, 7.744, 0.0), 4.5)])
		title = d.insert("1C", "IL-TB-ARCH-D", (0.0, 0.0, 0.0), 1.0, None, [("PROJECT", "Job", (30.0, 20.0, 0.0), 0.125)])
		other = d.insert("1E", "DOOR", (0.0, 0.0, 0.0), 1.0)

		self.assertEqual(self.lisp.call("il-rescale-symbols", 0.5), 1)

		self.assertEqual([d.value(tag, code) for code in (41, 42, 43)], [24.0, 24.0, 24.0])
		attribute = d.attribute(tag, "TAG")
		self.assertEqual(d.value(attribute, 40), 2.25)
		self.assertEqual(d.value(attribute, 10), (3.76, 8.872, 0.0))
		self.assertEqual(d.value(title, 41), 1.0)
		self.assertEqual(d.value(d.attribute(title, "PROJECT"), 40), 0.125)
		self.assertEqual(d.value(other, 41), 1.0)


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


def control(control_id, code, **extra):
	values = {"id": control_id, "handle": format(0x3A00 + int(control_id[-2:]) + (0x80 if control_id.startswith("DEC") else 0), "X"), "item_code": code, "start": "auto"}
	values.update(extra)
	return to_alist(values)


class Controls(unittest.TestCase):
	"""Controls in v1 (PRD question 7): placement, zones, DMX patch and control checks."""

	issues = Model.issues

	def setUp(self):
		Model.setUp(self)
		model = alist(self.model)
		model["controls"] = lst(
			[
				control("CTL-01", "DMXC-TW-BK-WALL", room="Z-Kitchen"),
				control("DEC-01", "DMXD-PWM-5C-SF", cabinet="CAB-1", universe=1, start=1, control_from="CTL-01"),
				control("DEC-02", "DMXD-PWM-5C-SF", cabinet="CAB-1", universe=1),
				control("DEC-03", "DMXD-PWM-5C-SF", cabinet="CAB-1", universe=1, start=11),
				control("CTL-02", "PIX-4", cabinet="CAB-1"),
			]
		)
		model["zones"] = lst(
			[
				to_alist({"id": "ZN-1", "name": "Kitchen", "method": "DMX512", "control": "CTL-01", "port": "DMX512", "runs": lst(["L1-01", "L1-02"])}),
				to_alist({"id": "ZN-2", "name": "Wrong", "method": "DMX512", "control": "CTL-02", "port": "OUT1", "runs": lst(["L2-01"])}),
				to_alist({"id": "ZN-3", "name": "Twice", "method": "0-10V", "runs": lst(["L1-02"])}),
			]
		)
		model["wires"] = lst([*model["wires"], to_alist({"id": "W-02", "from": "CTL-02", "to": "L3-01", "kind": "data", "length_in": 240.0})])
		self.model = to_alist(model)

	def test_dmx_patch_keeps_fixed_addresses_and_fills_auto_ones(self):
		patch = [plain(row) for row in self.lisp.call("il-dmx-patch", self.model, self.catalog)]
		self.assertEqual(patch, [[1, "DEC-01", 1, 5, None], [1, "DEC-02", 6, 10, True], [1, "DEC-03", 11, 15, None]])

	def test_control_checks(self):
		codes = {(issue["code"], issue["ref"]) for issue in self.issues()}
		self.assertIn(("PROTOCOL_MISMATCH", "ZN-2"), codes)  # DMX zone on an SPI output
		self.assertIn(("RUN_IN_TWO_ZONES", "L1-02"), codes)
		self.assertIn(("DATA_TOO_LONG", "W-02"), codes)  # 20 ft of pixel data, 15 ft allowed
		self.assertIn(("CONTROL_NO_SIGNAL", "DEC-02"), codes)
		self.assertNotIn(("CONTROL_NO_SIGNAL", "DEC-01"), codes)
		self.assertNotIn(("PROTOCOL_MISMATCH", "ZN-1"), codes)

	def test_overlap_and_full_universe(self):
		model = alist(self.model)
		model["controls"] = lst([control("DEC-01", "DMXD-PWM-5C-SF", universe=2, start=10), control("DEC-02", "DMXD-PWM-5C-SF", universe=2, start=12), control("DEC-03", "DMXD-PWM-5C-SF", universe=2, start=510)])
		model["zones"] = None
		self.model = to_alist(model)
		codes = {(issue["code"], issue["ref"]) for issue in self.issues()}
		self.assertIn(("DMX_ADDRESS_OVERLAP", "DEC-01"), codes)
		self.assertIn(("DMX_UNIVERSE_FULL", "DEC-03"), codes)

	def test_unknown_control(self):
		model = alist(self.model)
		model["controls"] = lst([control("CTL-09", "NOPE")])
		model["zones"] = None
		self.model = to_alist(model)
		self.assertIn(("CONTROL_UNKNOWN", "CTL-09"), {(issue["code"], issue["ref"]) for issue in self.issues()})

	def test_package_with_controls_and_zones_passes_the_portal_validator(self):
		model = alist(self.model)
		model["zones"] = lst(list(model["zones"])[:2])
		self.model = to_alist(model)
		issues = self.lisp.call("il-check", self.model, self.catalog, "2026-11-25")
		package = to_python_json(self.lisp.call("il-package", self.model, self.catalog, issues, "AutoCAD 2025"))
		with load_service(ROOT + ".system_design.ilq_schema") as (module, _frappe):
			self.assertEqual(module.validate_package(package), [])
		decoder = next(item for item in package["controls"] if item["id"] == "DEC-01")
		self.assertEqual(decoder["dmx"], {"universe": 1, "start_address": 1})
		self.assertEqual(decoder["control_from"], "CTL-01")
		self.assertEqual(next(item for item in package["controls"] if item["id"] == "DEC-02")["dmx"]["start_address"], "auto")
		self.assertEqual(package["zones"][0], {"id": "ZN-1", "name": "Kitchen", "method": "DMX512", "control": {"id": "CTL-01", "port": "DMX512"}, "runs": ["L1-01", "L1-02"]})

	def test_receipt_controls(self):
		receipt = from_python_json({"schema": "ilq-receipt/1", "runs": [], "controls": {"DEC-01": "LK9"}})
		self.assertEqual(plain(self.lisp.call("il-receipt-controls", receipt)), {"DEC-01": "LK9"})


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
	write-line zerop function handent
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
		spike = REPO / "tools/cad_toolkit/spike/il-spike.lsp"
		mini_lisp.read_all(spike.read_text(encoding="utf-8"))
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
