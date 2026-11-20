"""Draw-to-quote plan 6.1, 6.2: an ASCII DXF on ILM-* layers becomes an ilq/2 package."""

import json
import math
import types
import unittest

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".portal.dxf_ingest"


def dxf(units=1, entities=()):
	lines = ["0", "SECTION", "2", "HEADER"]
	if units is not None:
		lines += ["9", "$INSUNITS", "70", str(units)]
	lines += ["0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
	for entity in entities:
		lines += entity
	lines += ["0", "ENDSEC", "0", "EOF"]
	return "\n".join(lines)


def lwpolyline(layer, handle, points, closed=False):
	codes = ["0", "LWPOLYLINE", "5", handle, "8", layer, "90", str(len(points)), "70", "1" if closed else "0"]
	for point in points:
		codes += ["10", str(point[0]), "20", str(point[1])]
		if len(point) > 2 and point[2]:
			codes += ["42", str(point[2])]
	return codes


def line(layer, handle, a, b):
	return ["0", "LINE", "5", handle, "8", layer, "10", str(a[0]), "20", str(a[1]), "11", str(b[0]), "21", str(b[1])]


def arc(layer, handle, center, radius, start, end):
	return ["0", "ARC", "5", handle, "8", layer, "10", str(center[0]), "20", str(center[1]), "40", str(radius), "50", str(start), "51", str(end)]


def cabinet(handle, point, tag, rating):
	return [
		"0", "INSERT", "5", handle, "8", "ILM-CAB", "2", "IL-CABINET", "66", "1", "10", str(point[0]), "20", str(point[1]),
		"0", "ATTRIB", "8", "ILM-CAB", "2", "TAG", "1", tag,
		"0", "ATTRIB", "8", "ILM-CAB", "2", "RATING", "1", rating,
		"0", "SEQEND",
	]


def polyline(layer, handle, points):
	codes = ["0", "POLYLINE", "5", handle, "8", layer, "66", "1", "70", "0"]
	for point in points:
		codes += ["0", "VERTEX", "8", layer, "10", str(point[0]), "20", str(point[1]), "42", str(point[2] if len(point) > 2 else 0)]
	return [*codes, "0", "SEQEND"]


DRAWING = dxf(
	1,
	[
		lwpolyline("ILM-ROOM-Kitchen", "A1", [(0, 0), (200, 0), (200, 150), (0, 150)], closed=True),
		lwpolyline("ILM-ROOM-Living_Room", "A2", [(200, 0), (500, 0), (500, 150), (200, 150)], closed=True),
		cabinet("B1", (10, 10), "CAB-1", "damp"),
		lwpolyline("ILM-TAPE-led-hd-sw", "C1", [(10, 20, 0), (106, 20, 0)]),
		lwpolyline("ILM-TAPE-led-hd-sw", "C2", [(10, 50, math.tan(math.pi / 8)), (20, 60, 0), (60, 60, 0)]),
		line("ILM-TAPE-non-pnc-sw", "C3", (250, 20), (310, 20)),
		arc("ILM-TAPE-non-pnc-sw", "C4", (300, 100), 12, 0, 90),
		polyline("ILM-LINEAR-ILL-RA01-SW", "C5", [(220, 120), (316, 120)]),
		line("A-WALL", "D1", (0, 0), (10, 0)),
	],
)


class DxfReading(unittest.TestCase):
	def setUp(self):
		self.context = load_service(MODULE)
		self.module, self.frappe = self.context.__enter__()

	def tearDown(self):
		self.context.__exit__(None, None, None)

	def test_reads_rooms_cabinets_and_runs_in_inches(self):
		drawing = self.module.read_drawing(DRAWING)
		self.assertEqual([room["id"] for room in drawing["rooms"]], ["Z-Kitchen", "Z-Living-Room"])
		self.assertEqual(drawing["rooms"][1]["name"], "Living Room")
		self.assertEqual(drawing["cabinets"][0]["id"], "CAB-1")
		self.assertEqual(drawing["cabinets"][0]["rating"], "Damp")
		runs = {run["handle"]: run for run in drawing["runs"]}
		self.assertEqual(set(runs), {"C1", "C2", "C3", "C4", "C5"})
		self.assertEqual(runs["C1"]["length_in"], 96)
		self.assertAlmostEqual(runs["C2"]["length_in"], math.pi * 10 / 2 + 40, places=3)
		self.assertAlmostEqual(runs["C2"]["min_arc_radius_in"], 10, places=3)
		self.assertAlmostEqual(runs["C4"]["length_in"], math.pi * 12 / 2, places=3)
		self.assertEqual(runs["C5"]["template"], "ILL-RA01-SW")
		self.assertTrue(runs["C5"]["linear"])

	def test_units_convert_and_must_be_set(self):
		feet = self.module.read_drawing(dxf(2, [line("ILM-TAPE-x", "1", (0, 0), (8, 0))]))
		self.assertEqual(feet["runs"][0]["length_in"], 96)
		mm = self.module.read_drawing(dxf(4, [line("ILM-TAPE-x", "1", (0, 0), (2438.4, 0))]))
		self.assertAlmostEqual(mm["runs"][0]["length_in"], 96)
		for units in (None, 0, 3):
			with self.assertRaisesRegex(self.module.DxfError, "INSUNITS"):
				self.module.read_drawing(dxf(units, [line("ILM-TAPE-x", "1", (0, 0), (8, 0))]))

	def test_not_a_dxf(self):
		with self.assertRaises(self.module.DxfError):
			self.module.read_drawing("hello\nworld\nagain")

	def test_package_passes_the_validator_with_rooms_and_types(self):
		drawing = self.module.read_drawing(DRAWING)
		styles = {
			"ILM-TAPE-led-hd-sw": {"family": "LED Tape", "template": "led-hd-sw", "selections": {}},
			"ILM-TAPE-non-pnc-sw": {"family": "LED Neon", "template": "non-pnc-sw", "selections": {}},
			"ILM-LINEAR-ILL-RA01-SW": {"family": "Linear Fixture", "template": "ILL-RA01-SW", "selections": {}},
		}
		package = self.module.package_from_drawing(drawing, styles, {"ILM-TAPE-led-hd-sw": "L1"}, "job.dxf", "a" * 64, "0" * 64)
		with load_service(ROOT + ".system_design.ilq_schema") as (schema, _frappe):
			self.assertEqual(schema.validate_package(package), [])
		runs = {run["handle"]: run for run in package["runs"]}
		self.assertEqual(runs["C1"]["id"], "L1-01")
		self.assertEqual(runs["C1"]["room"], "Z-Kitchen")
		self.assertEqual(runs["C3"]["fixture_type"], "D3")
		self.assertEqual(runs["C3"]["location"], "Living Room")
		self.assertEqual(package["cabinets"][0], {"id": "CAB-1", "location_rating": "Damp", "room": "Z-Kitchen"})
		self.assertIn("min_arc_radius_in", runs["C2"]["segments"][0])

	def test_package_from_dxf_resolves_templates_and_presets(self):
		def get_value(doctype, filters, field):
			code = filters.get("template_code") if isinstance(filters, dict) else filters
			return {"led-hd-sw": "LED Tape", "non-pnc-sw": "LED Neon"}.get(code)

		self.frappe.db.get_value.side_effect = get_value
		presets = types.SimpleNamespace(
			load=lambda name: {
				"label": "RA01 27K",
				"request": {"family": "Linear Fixture", "template": "ILL-RA01-SW", "selections": {"finish_code": "BK"}, "segments": [{"end_type": "Endcap"}]},
				"problems": [],
			}
		)
		extras = {
			ROOT + ".portal.presets": presets,
			ROOT + ".system_design.catalog": types.SimpleNamespace(current_snapshot_hash=lambda: "0" * 63 + "1"),
		}
		with load_service(MODULE, extras) as (module, frappe):
			frappe.db.get_value.side_effect = get_value
			with self.assertRaisesRegex(module.DxfError, "linear fixtures need"):
				module.package_from_dxf(DRAWING.encode(), "job.dxf", {})
			package = module.package_from_dxf(DRAWING.encode(), "job.dxf", {"presets": {"ILM-LINEAR-ILL-RA01-SW": "PRE-1"}})
		linear = next(run for run in package["runs"] if run["handle"] == "C5")
		self.assertEqual(linear["style"]["preset"], "RA01 27K")
		self.assertEqual(linear["style"]["segments"], [{"end_type": "Endcap"}])
		neon = next(run for run in package["runs"] if run["handle"] == "C3")
		self.assertEqual(neon["style"], {"family": "LED Neon", "template": "non-pnc-sw", "selections": {}})
		self.assertTrue(package["drawing"]["hash"].startswith("sha256:"))

	def test_binary_dxf_and_no_runs_are_refused(self):
		with self.assertRaisesRegex(self.module.DxfError, "ASCII"):
			self.module.package_from_dxf(b"AutoCAD Binary DXF\r\n\x1a\x00", "job.dxf", {})
		with self.assertRaisesRegex(self.module.DxfError, "No runs"):
			self.module.package_from_drawing(self.module.read_drawing(dxf(1, [])), {}, {}, "job.dxf", "a" * 64, "0" * 64)


if __name__ == "__main__":
	unittest.main()
