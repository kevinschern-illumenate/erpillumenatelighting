"""Bluebeam spike probe and length comparison (draw-to-quote WP 2.2-2.6) on synthetic PDFs."""

import io
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
	sys.path.insert(0, str(REPO_ROOT))

from pypdf import PdfWriter
from pypdf.generic import (
	ArrayObject,
	DictionaryObject,
	FloatObject,
	NameObject,
	NumberObject,
	TextStringObject,
)

from tools.bluebeam_spike import compare_lengths, probe_pdf

# 1 in = 4 ft: 72 user space units (1 in of paper) are 4 ft, so X[0] /C = 4 / 72 ft per unit.
FT_PER_UNIT = 4 / 72


def name(value):
	return NameObject(value)


def numbers(*values):
	return ArrayObject(FloatObject(v) for v in values)


def number_format(unit, factor):
	return DictionaryObject(
		{
			name("/Type"): name("/NumberFormat"),
			name("/U"): TextStringObject(unit),
			name("/C"): FloatObject(factor),
			name("/D"): NumberObject(100),
		}
	)


def measure(x_factor=FT_PER_UNIT):
	return DictionaryObject(
		{
			name("/Type"): name("/Measure"),
			name("/Subtype"): name("/RL"),
			name("/R"): TextStringObject("1 in = 4 ft"),
			name("/X"): ArrayObject([number_format("ft", x_factor), number_format("in", 12)]),
			name("/D"): ArrayObject([number_format("ft", 1), number_format("in", 12)]),
			name("/A"): ArrayObject([number_format("sq ft", 1)]),
		}
	)


def build_pdf(*, annotate=True, encrypt=False, javascript=False, open_action=False):
	writer = PdfWriter()
	writer.add_blank_page(612, 792)  # page 1: blank
	page = writer.add_blank_page(1224, 792)  # page 2: plan with a viewport
	if annotate:
		page[name("/VP")] = ArrayObject(
			[
				DictionaryObject(
					{
						name("/Type"): name("/Viewport"),
						name("/BBox"): numbers(36, 36, 1188, 756),
						name("/Name"): TextStringObject("Level 1 Plan"),
						name("/Measure"): measure(),
					}
				)
			]
		)
		polyline = DictionaryObject(
			{
				name("/Type"): name("/Annot"),
				name("/Subtype"): name("/PolyLine"),
				name("/IT"): name("/PolyLineDimension"),
				name("/Subj"): TextStringObject("HD27-DRY"),
				name("/NM"): TextStringObject("ABCDEF0123456789"),
				name("/T"): TextStringObject("estimator"),
				name("/Contents"): TextStringObject("6' 0\""),
				name("/Rect"): numbers(95, 95, 177, 141),
				# 72 + 36 = 108 units = 1.5 in of paper = 6 ft = 72 in
				name("/Vertices"): numbers(100, 100, 172, 100, 172, 136),
				name("/BS"): DictionaryObject({name("/W"): FloatObject(2)}),
				name("/C"): numbers(1, 0, 0),
				name("/CreationDate"): TextStringObject("D:20261121090000-08'00'"),
				name("/M"): TextStringObject("D:20261121091500-08'00'"),
				name("/BSIColumnData"): ArrayObject([TextStringObject("L1-01"), TextStringObject("HD27")]),
			}
		)
		line = DictionaryObject(
			{
				name("/Type"): name("/Annot"),
				name("/Subtype"): name("/Line"),
				name("/IT"): name("/LineDimension"),
				name("/Subj"): TextStringObject("Length Measurement"),
				name("/Rect"): numbers(200, 200, 300, 260),
				# 3-4-5 triangle scaled by 18: 90 units = 5 ft; own /Measure at 1 in = 8 ft -> 10 ft
				name("/L"): numbers(200, 200, 254, 272),
				name("/Measure"): measure(8 / 72),
			}
		)
		page[name("/Annots")] = ArrayObject([writer._add_object(polyline), writer._add_object(line)])
	if javascript:
		writer.add_js("app.alert('hi');")
	if open_action:
		writer._root_object[name("/OpenAction")] = DictionaryObject(
			{name("/S"): name("/JavaScript"), name("/JS"): TextStringObject("app.alert(1)")}
		)
	if encrypt:
		writer.encrypt("secret", algorithm="RC4-128")
	buffer = io.BytesIO()
	writer.write(buffer)
	return buffer.getvalue()


class ProbeTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.report = probe_pdf.probe(build_pdf())

	def page(self, number):
		return self.report["pages"][number - 1]

	def test_report_is_json_safe(self):
		json.dumps(self.report)
		self.assertEqual(self.report["portal_checks"]["strict_parse"], "ok")
		self.assertEqual(self.report["portal_checks"]["pages"], 2)

	def test_blank_page_and_page_boxes(self):
		self.assertEqual(self.page(1)["annotations"], [])
		self.assertEqual(self.page(1)["viewports"], [])
		self.assertEqual(self.page(2)["MediaBox"], [0, 0, 1224, 792])
		self.assertEqual(self.page(2)["UserUnit"], 1.0)
		self.assertEqual(self.page(2)["rotation"], 0)
		self.assertEqual(self.page(2)["errors"], [])

	def test_viewport_and_measure(self):
		(viewport,) = self.page(2)["viewports"]
		self.assertEqual(viewport["Name"], "Level 1 Plan")
		self.assertEqual(viewport["BBox"], [36, 36, 1188, 756])
		self.assertEqual(viewport["Measure"]["Subtype"], "/RL")
		self.assertEqual(viewport["Measure"]["R"], "1 in = 4 ft")
		self.assertEqual([f["U"] for f in viewport["Measure"]["D"]], ["ft", "in"])
		self.assertAlmostEqual(viewport["Measure"]["X"][0]["C"], FT_PER_UNIT)

	def test_polyline_annotation(self):
		annot = self.page(2)["annotations"][0]
		self.assertEqual(annot["Subtype"], "/PolyLine")
		self.assertEqual(annot["IT"], "/PolyLineDimension")
		self.assertEqual(annot["Subj"], "HD27-DRY")
		self.assertEqual(annot["NM"], "ABCDEF0123456789")
		self.assertEqual(annot["vertices"], [[100, 100], [172, 100], [172, 136]])
		self.assertEqual(annot["vertex_source"], "/Vertices")
		self.assertEqual(annot["BS_width"], 2)
		self.assertEqual(annot["C"], [1, 0, 0])
		self.assertEqual(annot["measure_source"], "viewport[0]")
		self.assertEqual(annot["computed_unit"], "ft")
		self.assertAlmostEqual(annot["computed_length"], 6.0, places=6)
		self.assertAlmostEqual(annot["computed_length_in"], 72.0, places=6)
		self.assertAlmostEqual(annot["contents_length_in"], 72.0)
		self.assertEqual(annot["extra_keys"], {"/BSIColumnData": ["L1-01", "HD27"]})

	def test_annotation_measure_wins(self):
		annot = self.page(2)["annotations"][1]
		self.assertEqual(annot["vertices"], [[200, 200], [254, 272]])
		self.assertEqual(annot["vertex_source"], "/L")
		self.assertEqual(annot["measure_source"], "annotation")
		self.assertAlmostEqual(annot["computed_length"], 10.0, places=6)
		self.assertAlmostEqual(annot["computed_length_in"], 120.0, places=6)
		self.assertEqual(annot["extra_keys"], {})

	def test_summary(self):
		summary = self.report["summary"]
		self.assertEqual(summary["annotations"], 2)
		self.assertEqual(summary["by_subtype"], {"/PolyLine": 1, "/Line": 1})
		self.assertEqual(summary["by_intent"]["/PolyLineDimension"], 1)
		self.assertEqual(summary["by_subject"]["HD27-DRY"], 1)
		self.assertEqual(summary["extra_key_names"], {"/BSIColumnData": 1})
		self.assertEqual(summary["measured_markups"], 2)
		self.assertFalse(summary["flattened_or_empty"])
		self.assertTrue(summary["has_viewports"])
		self.assertTrue(summary["has_measures"])

	def test_flattened_or_empty(self):
		summary = probe_pdf.probe(build_pdf(annotate=False))["summary"]
		self.assertTrue(summary["flattened_or_empty"])
		self.assertFalse(summary["has_viewports"])
		self.assertFalse(summary["has_measures"])

	def test_refusals(self):
		cases = {
			"encrypted": build_pdf(encrypt=True),
			"javascript": build_pdf(javascript=True),
			"open action": build_pdf(open_action=True),
			"not a pdf": b"hello",
			"empty": b"",
		}
		for label, content in cases.items():
			with self.subTest(label), self.assertRaises(probe_pdf.PdfRefused):
				probe_pdf.probe(content)
		with self.assertRaisesRegex(probe_pdf.PdfRefused, "Encrypted"):
			probe_pdf.probe(build_pdf(encrypt=True))
		with self.assertRaisesRegex(probe_pdf.PdfRefused, "actions"):
			probe_pdf.probe(build_pdf(javascript=True))

	def test_malformed_values_are_recorded_not_raised(self):
		writer = PdfWriter()
		page = writer.add_blank_page(612, 792)
		page[name("/VP")] = ArrayObject([TextStringObject("not a dict")])
		page[name("/Annots")] = ArrayObject(
			[
				writer._add_object(
					DictionaryObject(
						{
							name("/Subtype"): name("/PolyLine"),
							name("/Vertices"): numbers(1, 2, 3),
							name("/Rect"): ArrayObject([TextStringObject("x")]),
						}
					)
				)
			]
		)
		buffer = io.BytesIO()
		writer.write(buffer)
		page_report = probe_pdf.probe(buffer.getvalue())["pages"][0]
		self.assertEqual(len(page_report["annotations"]), 1)
		joined = " ".join(page_report["errors"])
		self.assertIn("VP[0]", joined)
		self.assertIn("vertices", joined)
		self.assertIn("/Rect", joined)

	def test_length_text_parser(self):
		cases = {
			"12' 6\"": 150,
			"12'-6 1/2\"": 150.5,
			"Run L1-01 12.5'": 150,
			'150.25"': 150.25,
			"3.81 m": 3.81 / 0.0254,
			"HD27-DRY": None,
		}
		for value, expected in cases.items():
			with self.subTest(value):
				result = probe_pdf.parse_length_text(value)
				if expected is None:
					self.assertIsNone(result)
				else:
					self.assertAlmostEqual(result, expected, places=4)


def annotation(index, length_in, **fields):
	return {
		"index": index,
		"Subtype": "/PolyLine",
		"computed_length_in": length_in,
		"extra_keys": {},
		**fields,
	}


class CompareTests(unittest.TestCase):
	def setUp(self):
		self.package = {
			"schema": "ilq/2",
			"runs": [
				{"id": "R-1", "segments": [{"path_length_in": 100}]},
				{"id": "R-2", "segments": [{"path_length_in": 200}]},
				{"id": "R-3", "segments": [{"path_length_in": 30}, {"path_length_in": 20}]},
			],
		}
		self.report = {
			"pages": [
				{
					"page": 1,
					"annotations": [
						annotation(0, 198, NM="a", extra_keys={"/BSIColumnData": ["R-2", "HD27"]}),
						annotation(1, 101, NM="b", Contents="Run R-1"),
						{"index": 2, "Subtype": "/Polygon", "computed_length_in": 999, "extra_keys": {}},
					],
				},
				{"page": 2, "annotations": [annotation(0, 51, NM="c", Subj="HD27-DRY")]},
			]
		}

	def test_matching_and_errors(self):
		result = compare_lengths.compare(self.report, self.package)
		rows = {row["run_id"]: row for row in result["runs"]}
		self.assertEqual(rows["R-1"]["method"], "id")
		self.assertEqual(rows["R-2"]["method"], "id")
		self.assertEqual(rows["R-3"]["method"], "order")
		self.assertEqual(rows["R-3"]["truth_in"], 50)
		self.assertAlmostEqual(rows["R-1"]["error_pct"], 1.0)
		self.assertAlmostEqual(rows["R-2"]["error_pct"], -1.0)
		self.assertAlmostEqual(rows["R-2"]["error_in"], -2.0)
		self.assertAlmostEqual(rows["R-3"]["error_pct"], 2.0)
		self.assertEqual(result["unmatched_markups"], [])

	def test_summary_statistics(self):
		summary = compare_lengths.compare(self.report, self.package, tolerance_pct=1.0)["summary"]
		self.assertEqual(summary["matched"], 3)
		self.assertEqual((summary["matched_by_id"], summary["matched_by_order"]), (2, 1))
		self.assertAlmostEqual(summary["mean_error_pct"], 2 / 3, places=5)
		self.assertAlmostEqual(summary["mean_abs_error_pct"], 4 / 3, places=5)
		self.assertAlmostEqual(summary["max_abs_error_pct"], 2.0)
		self.assertAlmostEqual(summary["p95_abs_error_pct"], 2.0)
		self.assertAlmostEqual(summary["max_abs_error_in"], 2.0)
		self.assertEqual(summary["within_tolerance"], 2)

	def test_same_id_markups_are_summed_and_extras_reported(self):
		self.report["pages"][1]["annotations"] = [
			annotation(0, 30, Contents="R-3"),
			annotation(1, 20.5, Contents="R-3"),
			annotation(2, 40),
		]
		result = compare_lengths.compare(self.report, self.package)
		row = next(row for row in result["runs"] if row["run_id"] == "R-3")
		self.assertAlmostEqual(row["computed_in"], 50.5)
		self.assertEqual(len(row["markups"]), 2)
		self.assertEqual(result["unmatched_markups"], [{"page": 2, "index": 2, "NM": None, "length_in": 40}])

	def test_percentile_and_rejects_other_schema(self):
		self.assertEqual(compare_lengths.percentile_nearest_rank(list(range(1, 21)), 95), 19)
		with self.assertRaises(ValueError):
			compare_lengths.truth_runs({"schema": "ilq/1", "runs": []})

	def test_round_trip_from_probe(self):
		report = probe_pdf.probe(build_pdf())
		package = {
			"schema": "ilq/2",
			"runs": [{"id": "L1-01", "segments": [{"path_length_in": 72}]}],
		}
		result = compare_lengths.compare(report, package, subtypes=("/PolyLine",))
		self.assertEqual(result["runs"][0]["method"], "id")
		self.assertAlmostEqual(result["runs"][0]["error_pct"], 0.0, places=6)
		self.assertIn("| L1-01 |", compare_lengths.to_markdown(result))


if __name__ == "__main__":
	unittest.main()
