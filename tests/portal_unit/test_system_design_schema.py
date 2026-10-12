"""Design document contract parity with the TypeScript package (System Designer H5, WP-2.2)."""

import copy
import json
import unittest
from pathlib import Path

from test_services import ROOT, load_service

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tools/system_designer/packages/core-schemas/fixtures/designs"
SCHEMA = ROOT + ".system_design.design_schema"


def fixture(path):
	return json.loads((FIXTURES / path).read_text(encoding="utf-8"))


class DesignContract(unittest.TestCase):
	def setUp(self):
		self.context = load_service(SCHEMA)
		self.module, _frappe = self.context.__enter__()

	def tearDown(self):
		self.context.__exit__(None, None, None)

	def test_python_accepts_and_rejects_the_same_fixtures(self):
		for path in sorted((FIXTURES / "valid").glob("*.json")):
			with self.subTest(path.name):
				self.assertEqual(self.module.validate_design_json(fixture(f"valid/{path.name}")), [])
		for path in sorted((FIXTURES / "invalid").glob("*.json")):
			with self.subTest(path.name):
				self.assertNotEqual(self.module.validate_design_json(fixture(f"invalid/{path.name}")), [])

	def test_hash_parity_with_typescript(self):
		for name, expected in fixture("hashes.json").items():
			with self.subTest(name):
				self.assertEqual(self.module.build_hash(fixture(f"valid/{name}")), expected)

	def test_views_and_sub_millesimal_changes_do_not_change_the_hash(self):
		design = fixture("valid/runs-and-site.json")
		expected = fixture("hashes.json")["runs-and-site.json"]
		self.assertEqual(self.module.build_hash({**design, "views": {"saved3d": []}}), expected)
		design["runs"][0]["lengthFt"] = 12.3457
		self.assertEqual(self.module.build_hash(design), expected)
		design["runs"][0]["lengthFt"] = 12.4
		self.assertNotEqual(self.module.build_hash(design), expected)

	def test_canonical_json_matches_javascript_rules(self):
		self.assertEqual(
			self.module.canonical_json({"b": 1.23456, "a": [3.0, -0.0001, None], "d": "é", "t": True}),
			'{"a":[3,0,null],"b":1.235,"d":"é","t":true}',
		)
		for value, expected in fixture("rounding.json"):
			self.assertEqual(self.module.round_number(value), expected, value)
		with self.assertRaises(ValueError):
			self.module.canonical_json({"a": float("nan")})

	def test_vd_targets_cannot_be_looser_than_settings(self):
		design = fixture("valid/minimal.json")
		design["project"]["settings"]["vdTargetLowVoltagePct"] = 4
		limits = {"vd_target_class2_pct": 3.0, "vd_target_line_pct": 3.0, "vd_target_landscape_pct": 5.0}
		problems = self.module.validate_design_json(design, limits)
		self.assertEqual(len(problems), 1)
		self.assertIn("vdTargetLowVoltagePct", problems[0])
		design["project"]["settings"]["vdTargetLowVoltagePct"] = 2
		self.assertEqual(self.module.validate_design_json(design, limits), [])
		design["project"]["settings"]["vdTargetLowVoltagePct"] = 4
		design["overrides"] = [
			{
				"code": "VD_TARGET_LOOSENED",
				"entityRef": "project",
				"kind": "staff-override",
				"reason": "Engineer approved",
				"by": "ae@example.com",
				"at": "2026-10-09T12:00:00Z",
			}
		]
		self.assertEqual(self.module.validate_design_json(design, limits), [])

	def test_problems_name_the_path(self):
		design = copy.deepcopy(fixture("valid/runs-and-site.json"))
		design["runs"][2]["watts"] = -1
		(problem,) = self.module.validate_design_json(design)
		self.assertTrue(problem.startswith("runs/2/watts"), problem)


if __name__ == "__main__":
	unittest.main()
