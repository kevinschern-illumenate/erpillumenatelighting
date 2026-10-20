"""Linear runs are split so every run fits an eligible supply output."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.power_planner import plan_power

UNIV_100 = {
	"item_code": "PS-UNIV-24V-100W-IP66",
	"outputs_count": 1,
	"max_wattage": 100,
	"max_wattage_per_output": 100,
	"usable_load_factor": 0.8,
}
UNIV_200 = {
	"item_code": "PS-UNIV-24V-200W-IP66",
	"outputs_count": 2,
	"max_wattage": 200,
	"max_wattage_per_output": 100,
	"usable_load_factor": 0.8,
}
UNIV_30 = {
	"item_code": "PS-UNIV-24V-30W-IP66",
	"outputs_count": 1,
	"max_wattage": 30,
	"max_wattage_per_output": 30,
	"usable_load_factor": 0.8,
}
WATTS_PER_FT = 6.4
TOTAL_FT = 85 / WATTS_PER_FT + 2.45


def split(limit):
	"""The engine's full-runs-then-remainder split at a per-run watt limit."""
	max_ft = limit / WATTS_PER_FT
	runs, left = [], TOTAL_FT
	while left > 1e-9:
		length = min(max_ft, left)
		runs.append({"run_key": str(len(runs) + 1), "watts": round(length * WATTS_PER_FT, 2)})
		left -= length
	return runs


def linear_power(found):
	catalog = types.SimpleNamespace(candidates=MagicMock(return_value=(found, {})))
	return load_service(ROOT + ".api.linear_power", {ROOT + ".api.driver_catalog": catalog})


class RunWattLimit(unittest.TestCase):
	def limit(self, found, protocol=None):
		with linear_power(found) as (module, frappe):
			frappe.get_doc.return_value = Record(input_voltage="24VDC", input_protocol="PWM")
			return module.run_watt_limit("ILL-SH01-SW", Record(tape_spec="TAPE"), protocol)

	def test_largest_usable_eligible_output_sets_the_run_limit(self):
		self.assertAlmostEqual(self.limit([UNIV_30, UNIV_200]), 80)

	def test_total_rating_caps_a_single_output(self):
		small_total = {**UNIV_200, "max_wattage": 60}
		self.assertAlmostEqual(self.limit([small_total]), 48)

	def test_large_supplies_never_raise_the_historic_ceiling(self):
		big = {**UNIV_100, "max_wattage": 300, "max_wattage_per_output": 300}
		self.assertEqual(self.limit([big]), 85)

	def test_no_eligible_supply_keeps_the_historic_ceiling(self):
		self.assertEqual(self.limit([]), 85)


class ReportedRun(unittest.TestCase):
	"""15.75 ft of 6.4 W/ft tape on a template whose supplies give 80 W per output."""

	def test_85_w_runs_fit_no_supply_output(self):
		runs = split(85)
		self.assertEqual([r["watts"] for r in runs], [85, 15.68])
		with self.assertRaisesRegex(ValueError, "No compatible supply allocation"):
			plan_power(runs, [UNIV_100, UNIV_200, UNIV_30])

	def test_runs_split_at_the_output_limit_share_one_two_output_supply(self):
		runs = split(80)
		self.assertEqual([r["watts"] for r in runs], [80, 20.68])
		plan = plan_power(runs, [UNIV_100, UNIV_200, UNIV_30])
		self.assertEqual(plan["drivers"], [{"driver_item": "PS-UNIV-24V-200W-IP66", "qty": 1}])
		self.assertEqual([(a["supply"], a["output"]) for a in plan["allocations"]], [(1, 1), (1, 2)])

	def test_without_a_multi_output_supply_each_run_gets_its_own(self):
		plan = plan_power(split(80), [UNIV_100, UNIV_30])
		self.assertEqual(
			plan["drivers"],
			[
				{"driver_item": "PS-UNIV-24V-100W-IP66", "qty": 1},
				{"driver_item": "PS-UNIV-24V-30W-IP66", "qty": 1},
			],
		)


if __name__ == "__main__":
	unittest.main()
