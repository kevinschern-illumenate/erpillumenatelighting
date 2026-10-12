"""Supplies eligible for runs (System Designer §10.1, H6 ``eligible_supplies``, WP-3.4)."""

import json
import unittest
from pathlib import Path

from test_services import ROOT, load_service

SUPPLIES = ROOT + ".system_design.supplies"
FIXTURES = Path(__file__).resolve().parents[2] / "tools/system_designer/packages/core-schemas/fixtures"
OPENED = json.loads((FIXTURES / "open-design/expected.json").read_text(encoding="utf-8"))
ITEMS = {
	item["id"]: item
	for item in json.loads((FIXTURES / "catalog/payload.json").read_text(encoding="utf-8"))["items"]
}
LINEAR = ("ilL-Fixture-Template", "TPL-LINEAR")
GROUP = ("ilL-Fixture-Template", "TPL-GROUP")


def builds():
	result = json.loads(json.dumps(OPENED["builds"]))
	result["ilL-Configured-Fixture"]["ILL-CF-LINEAR"]["template"] = LINEAR
	result["ilL-Configured-Group"]["ILL-CG-00001"]["template"] = GROUP
	return result


class Requirements(unittest.TestCase):
	def test_reads_voltage_template_and_supply_dimmed_protocols(self):
		with load_service(SUPPLIES) as (module, _frappe):
			reqs = module.requirements(
				["a1linear:1:1", "a1linear:2:1", "d1group:1:1", "b1tape:1:1"],
				OPENED["lines"],
				builds(),
				ITEMS,
			)
		self.assertEqual(
			reqs,
			[
				{"voltage": 24, "template": LINEAR, "protocols": []},
				{"voltage": 24, "template": GROUP, "protocols": ["0-10V"]},
				# DMX tape dims through a decoder, so the supply needs no protocol.
				{"voltage": 24, "template": None, "protocols": []},
			],
		)

	def test_refuses_line_voltage_unknown_runs_and_bad_keys(self):
		with load_service(SUPPLIES) as (module, _frappe):
			with self.assertRaisesRegex(module.DesignError, "line voltage"):
				module.requirements(["e1other:1:1"], OPENED["lines"], builds(), ITEMS)
			with self.assertRaisesRegex(module.DesignError, "not on this schedule"):
				module.requirements(["zz:1:1"], OPENED["lines"], builds(), ITEMS)
			for bad in ([], "nope", ["a1linear"], [f"x{i}:1:1" for i in range(1001)]):
				with self.assertRaises(module.DesignError):
					module.parse_run_keys(bad)
			self.assertEqual(module.parse_run_keys('["b:1:1", "a:1:1", "b:1:1"]'), ["a:1:1", "b:1:1"])


class Eligible(unittest.TestCase):
	def run_eligible(self, reqs, allowed, locations=None, rating=None):
		with load_service(SUPPLIES) as (module, _frappe):
			return module.eligible(reqs, ITEMS, allowed, locations or {}, rating)

	def test_filters_by_template_protocol_and_location_with_rank_only(self):
		linear = {"voltage": 24, "template": LINEAR, "protocols": []}
		allowed = {LINEAR: {"TEST-PSU-60", "TEST-PSU-96", "TEST-PSU-BAD"}}
		rows = self.run_eligible([linear], allowed, {"TEST-PSU-96": "Damp"})
		self.assertEqual(
			rows,
			[
				{
					"catalog_id": "drv:TEST-PSU-60",
					"item_code": "TEST-PSU-60",
					"rank": 1,
					"location_rating": "Dry",
				},
				{
					"catalog_id": "drv:TEST-PSU-96",
					"item_code": "TEST-PSU-96",
					"rank": 2,
					"location_rating": "Damp",
				},
			],
		)
		self.assertNotIn("cost", json.dumps(rows))
		damp = self.run_eligible([linear], allowed, {"TEST-PSU-96": "Damp"}, "Damp")
		self.assertEqual([row["catalog_id"] for row in damp], ["drv:TEST-PSU-96"])
		self.assertEqual(self.run_eligible([linear], {LINEAR: {"TEST-PSU-96"}}, {}, "Wet"), [])

		dimmed = {"voltage": 24, "template": LINEAR, "protocols": ["0-10V"]}
		self.assertEqual(
			[row["catalog_id"] for row in self.run_eligible([dimmed], allowed)], ["drv:TEST-PSU-96"]
		)
		wrong_volts = {"voltage": 12, "template": None, "protocols": []}
		self.assertEqual(self.run_eligible([wrong_volts], allowed), [])
		third_party = {"voltage": 24, "template": None, "protocols": []}
		self.assertEqual(len(self.run_eligible([linear, third_party], {LINEAR: {"TEST-PSU-60"}})), 1)


if __name__ == "__main__":
	unittest.main()
