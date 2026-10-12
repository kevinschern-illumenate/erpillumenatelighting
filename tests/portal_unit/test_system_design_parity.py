"""Golden parity: the Python verification mirror agrees with the designer engine (plan H10, §18.2, WP-3.6)."""

import json
import unittest
from pathlib import Path

from test_services import ROOT, load_service

VERIFY = ROOT + ".system_design.verify"
REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "tools/system_designer/fixtures/golden"
NEC = REPO / "tools/system_designer/packages/data/src/nec"
TABLES = REPO / "illumenate_lighting/illumenate_lighting/system_design/code_tables"
CASES = sorted(path.name.removesuffix(".input.json") for path in GOLDEN.glob("*.input.json"))


def read(path):
	return json.loads(path.read_text(encoding="utf-8"))


class GoldenParity(unittest.TestCase):
	def test_every_case_has_an_expected_file(self):
		self.assertGreaterEqual(len(CASES), 10)
		for name in CASES:
			self.assertTrue((GOLDEN / f"{name}.expected.json").exists(), name)

	def test_mirror_matches_the_engine_on_every_golden_case(self):
		with load_service(VERIFY) as (module, _frappe):
			for name in CASES:
				case = read(GOLDEN / f"{name}.input.json")
				expected = read(GOLDEN / f"{name}.expected.json")["verify"]
				with self.subTest(case=name):
					server = module.subset(case["design"], case["products"], case["wires"], case["limits"])
					self.assertEqual(server, expected)
					self.assertEqual(module.compare(expected, server), [])

	def test_dealer_items_match_the_engine(self):
		lines = read(REPO / "tools/system_designer/packages/core-schemas/fixtures/open-design/expected.json")[
			"lines"
		]
		products = read(GOLDEN / "third-party-mixed.input.json")["products"]
		engine = {item["id"]: item["specs"] for item in products if item["id"].startswith("tp:")}
		with load_service(VERIFY) as (module, _frappe):
			mirror = {item["id"]: item["specs"] for item in module.dealer_items(lines)}
		self.assertEqual(mirror["tp:e1other"], engine["tp:e1other"])
		self.assertEqual(mirror["tp:f1other"]["kind"], "incomplete")

	def test_code_tables_are_the_designer_copies(self):
		names = sorted(path.name for path in NEC.glob("*.json"))
		self.assertEqual(sorted(path.name for path in TABLES.glob("*.json")), names)
		for name in names:
			self.assertEqual(read(TABLES / name), read(NEC / name), name)


class Compare(unittest.TestCase):
	def test_reports_each_difference_with_both_values(self):
		server = {
			"loading": [{"entityId": "PS-1", "port": "OUT1", "wattsW": 88}],
			"runs": {"power:load:a": {"wireTypeId": "wire:14", "vdPct": 2.5}},
			"messages": ["PSU_ABOVE_DERATE|PS-1"],
			"review": [],
		}
		client = {
			"loading": [{"entityId": "PS-1", "port": "OUT1", "wattsW": 88.004}],
			"runs": {"power:load:a": {"wireTypeId": "wire:18", "vdPct": 6.1}},
			"messages": ["PSU_OVERLOAD|PS-1"],
			"review": ["DMX"],
		}
		with load_service(VERIFY) as (module, _frappe):
			self.assertEqual(module.compare(server, server), [])
			mismatches = module.compare(client, server)
		self.assertEqual(
			[(item["code"], item["entityRef"], item["client"], item["server"]) for item in mismatches],
			[
				("WIRE", "power:load:a", "wire:18", "wire:14"),
				("VOLTAGE_DROP", "power:load:a", 6.1, 2.5),
				("PSU_ABOVE_DERATE", "PS-1", False, True),
				("PSU_OVERLOAD", "PS-1", True, False),
				("REVIEW", "project", ["DMX"], []),
			],
		)


class Targets(unittest.TestCase):
	def test_project_targets_tighten_and_only_staff_loosen(self):
		design = {
			"project": {"settings": {"vdTargetLowVoltagePct": 2, "vdTargetLineVoltagePct": 5}},
			"overrides": [],
		}
		with load_service(VERIFY) as (module, _frappe):
			limits = module.vd_limits(
				{"vd_target_class2_pct": 3, "vd_target_line_pct": 3, "vd_target_landscape_pct": 0}
			)
			self.assertEqual(
				limits, {"vdTargetLowVoltagePct": 3, "vdTargetLineVoltagePct": 3, "vdTargetLandscapePct": 5}
			)
			self.assertEqual(
				module.effective_targets(design, limits),
				{"vdTargetLowVoltagePct": 2, "vdTargetLineVoltagePct": 3, "vdTargetLandscapePct": 5},
			)
			design["overrides"] = [{"code": "VD_TARGET_LOOSENED", "kind": "staff-override"}]
			self.assertEqual(module.effective_targets(design, limits)["vdTargetLineVoltagePct"], 5)


if __name__ == "__main__":
	unittest.main()
