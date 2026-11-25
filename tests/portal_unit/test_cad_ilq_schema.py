"""``ilq/2`` package contract parity with the TypeScript schema (draw-to-quote plan 1.5)."""

import copy
import json
import unittest
from pathlib import Path

from test_services import ROOT, load_service

FIXTURES = Path(__file__).resolve().parents[2] / "tools/system_designer/fixtures/cad/packages"


def fixture(path):
	return json.loads((FIXTURES / path).read_text(encoding="utf-8"))


class IlqContract(unittest.TestCase):
	def setUp(self):
		self.context = load_service(ROOT + ".system_design.ilq_schema")
		self.module, _frappe = self.context.__enter__()

	def tearDown(self):
		self.context.__exit__(None, None, None)

	def test_python_accepts_and_rejects_the_same_fixtures(self):
		for path in sorted((FIXTURES / "valid").glob("*.json")):
			with self.subTest(path.name):
				self.assertEqual(self.module.validate_package(fixture(f"valid/{path.name}")), [])
		for path in sorted((FIXTURES / "invalid").glob("*.json")):
			with self.subTest(path.name):
				self.assertNotEqual(self.module.validate_package(fixture(f"invalid/{path.name}")), [])

	def test_parse_fills_defaults(self):
		package = self.module.parse_package(json.dumps(fixture("valid/minimal.json")))
		self.assertEqual(package["rooms"], [])
		self.assertEqual(package["runs"][0]["segments"][0]["end_type"], "ENDCAP")
		self.assertEqual(package["runs"][0]["feed"], {"method": "end", "point_handles": []})
		self.assertEqual(package["target"], {"schedule": "", "schedule_version": 0, "project": ""})

	def test_problems_name_the_path(self):
		with self.assertRaises(self.module.PackageError) as caught:
			self.module.parse_package(fixture("invalid/unknown-room.json"))
		self.assertIn("runs/0/room", caught.exception.problems[0])

	def test_size_and_json_limits(self):
		with self.assertRaisesRegex(self.module.PackageError, "5 MB"):
			self.module.parse_package("x" * (5 * 1024 * 1024 + 1))
		with self.assertRaisesRegex(self.module.PackageError, "not valid JSON"):
			self.module.parse_package("{")

	def test_handles_are_unique_ignoring_case(self):
		package = fixture("valid/minimal.json")
		run = copy.deepcopy(package["runs"][0])
		run.update(id="T1-02", handle="1a")
		package["runs"].append(run)
		self.assertTrue(any("Duplicate handle" in problem for problem in self.module.validate_package(package)))

	def test_sources_are_derived_for_old_packages(self):
		package = self.module.parse_package(fixture("valid/minimal.json"))
		self.assertEqual(package["source"]["tool"], "autocad")
		self.assertEqual(package["source"]["input"], "ilq")
		self.assertEqual(package["sheets"], [])
		self.assertEqual(package["counts"], [])
		dxf = fixture("valid/minimal.json")
		dxf["toolkit"] = {"version": "dxf-1", "platform": "DXF upload"}
		self.assertEqual(self.module.parse_package(dxf)["source"]["tool"], "dxf")

	def test_sheets_counts_and_scale_claims(self):
		package = self.module.parse_package(fixture("valid/sheets-two-levels.json"))
		self.assertEqual([sheet["id"] for sheet in package["sheets"]], ["L1", "L2"])
		self.assertEqual(package["source"]["tool"], "autocad")
		for name, path in (
			("unknown-sheet.json", "runs/1/sheet"),
			("count-unknown-room.json", "counts/0/room"),
			("scale-claim-mismatch.json", "sheets/1/scale/status"),
		):
			with self.subTest(name):
				problems = self.module.validate_package(fixture(f"invalid/{name}"))
				self.assertTrue(any(problem.startswith(path) for problem in problems), problems)

	def test_twenty_run_job(self):
		package = self.module.parse_package(fixture("valid/job-20-runs.json"))
		self.assertEqual(len(package["runs"]), 20)
		self.assertEqual({run["style"]["family"] for run in package["runs"]}, {"LED Tape", "LED Neon", "COB Tape", "Extrusion Kit", "Linear Fixture"})


	def test_groups_and_stacked_copies(self):
		package = self.module.parse_package(fixture("valid/group-stack.json"))
		self.assertEqual(package["runs"][0]["copies"], 4)
		self.assertEqual(package["groups"][0]["power"], {"include_supplies": True, "allocation": "grouped"})
		self.assertEqual(package["groups"][0]["erp"], {})
		# Packages without groups get the defaults, so the import reads every key the same way.
		plain = self.module.parse_package(fixture("valid/minimal.json"))
		self.assertEqual(plain["groups"], [])
		self.assertEqual(plain["runs"][0]["copies"], 1)
		for name, problem in (
			("group-unknown-run.json", "groups/0/runs/1: Unknown run: T9-99"),
			("group-run-twice.json", "groups/1/runs/0: Run is in two groups: T1-01"),
			("group-too-many.json", "groups/0/runs: A group holds at most 12 runs, copies included"),
			("group-copies-without-group.json", "runs/0/copies: Stacked run T1-01 is in no group"),
			("group-id-clash.json", "groups: Group id is used elsewhere: PS-01"),
		):
			with self.subTest(name):
				problems = self.module.validate_package(fixture(f"invalid/{name}"))
				self.assertTrue(any(p.startswith(problem) for p in problems), problems)

	def test_a_wire_may_end_at_a_group(self):
		package = fixture("valid/group-stack.json")
		self.assertEqual(package["wire_paths"][0]["to"], "G-01")
		self.assertEqual(self.module.validate_package(package), [])


if __name__ == "__main__":
	unittest.main()
