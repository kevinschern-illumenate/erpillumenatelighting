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

	def test_twenty_run_job(self):
		package = self.module.parse_package(fixture("valid/job-20-runs.json"))
		self.assertEqual(len(package["runs"]), 20)
		self.assertEqual({run["style"]["family"] for run in package["runs"]}, {"LED Tape", "LED Neon", "COB Tape", "Extrusion Kit", "Linear Fixture"})


if __name__ == "__main__":
	unittest.main()
