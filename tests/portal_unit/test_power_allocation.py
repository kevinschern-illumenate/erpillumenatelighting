"""Per-run versus grouped supply allocation for every product family."""

import itertools
import json
import random
import time
import types
import unittest
from unittest.mock import MagicMock, patch

from test_fixture_groups import request
from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint
from illumenate_lighting.illumenate_lighting.api.group_contract import normalize
from illumenate_lighting.illumenate_lighting.api.power_planner import (
	GROUPED,
	PER_RUN,
	allocation_mode,
	plan_power,
)


def supply(item, watts, per_output, outputs, cost=0, factor=0.8):
	return {
		"item_code": item,
		"max_wattage": watts,
		"max_wattage_per_output": per_output,
		"outputs_count": outputs,
		"usable_load_factor": factor,
		"cost": cost,
	}


# A 3 x 100 W supply and two single-output supplies, as in the reported multi-run group.
TRIPLE = supply("PS-300W-3x100", 300, 100, 3, cost=90)
SMALL = supply("PS-30W", 30, 30, 1, cost=20)
SINGLE = supply("PS-100W", 100, 100, 1, cost=40)
CATALOG = [TRIPLE, SMALL, SINGLE]


def circuits(*loads):
	return [{"run_key": str(i), "watts": load} for i, load in enumerate(loads, 1)]


def check(test, plan, candidates):
	"""Every circuit is on exactly one output, and no output or supply exceeds its usable rating."""
	by_item = {c["item_code"]: c for c in candidates}
	test.assertEqual(
		sorted(a["run_key"] for a in plan["allocations"]), sorted(r["run_key"] for r in plan["requirements"])
	)
	supplies = {}
	for a in plan["allocations"]:
		supplies.setdefault(a["supply"], {"item": a["item_code"], "outputs": {}})
		outputs = supplies[a["supply"]]["outputs"]
		outputs[a["output"]] = outputs.get(a["output"], 0) + a["watts"]
	for row in supplies.values():
		spec = by_item[row["item"]]
		factor = spec["usable_load_factor"]
		test.assertLessEqual(sum(row["outputs"].values()), spec["max_wattage"] * factor + 1e-9)
		test.assertLessEqual(max(row["outputs"]), spec["outputs_count"])
		for watts in row["outputs"].values():
			test.assertLessEqual(watts, spec["max_wattage_per_output"] * factor + 1e-9)
	counts = {}
	for row in supplies.values():
		counts[row["item"]] = counts.get(row["item"], 0) + 1
	test.assertEqual({d["driver_item"]: d["qty"] for d in plan["drivers"]}, counts)
	return supplies


class AllocationModes(unittest.TestCase):
	def test_reported_three_small_runs_share_one_output_of_a_small_supply(self):
		per_run = plan_power(circuits(3, 3, 3), CATALOG)
		self.assertEqual(per_run["drivers"], [{"driver_item": "PS-300W-3x100", "qty": 1}])
		self.assertEqual([a["output"] for a in per_run["allocations"]], [1, 2, 3])
		grouped = plan_power(circuits(3, 3, 3), CATALOG, allocation=GROUPED)
		self.assertEqual(grouped["drivers"], [{"driver_item": "PS-30W", "qty": 1}])
		self.assertEqual({(a["supply"], a["output"]) for a in grouped["allocations"]}, {(1, 1)})
		self.assertEqual(grouped["allocation"], GROUPED)
		check(self, grouped, CATALOG)

	def test_per_run_stays_the_default_and_its_plan_is_unchanged(self):
		for mode in (None, "", PER_RUN, " Per_Run "):
			with self.subTest(mode=mode):
				plan = plan_power(circuits(3, 3, 3), CATALOG, allocation=mode)
				self.assertNotIn("allocation", plan)
				self.assertEqual(plan, plan_power(circuits(3, 3, 3), CATALOG))
		with self.assertRaisesRegex(ValueError, "per_run or grouped"):
			allocation_mode("shared")

	def test_grouping_respects_the_per_output_limit(self):
		# 50 + 30 fills one 80 W output; the 60 W run needs a second output.
		plan = plan_power(circuits(50, 30, 60), [TRIPLE], allocation=GROUPED)
		self.assertEqual(plan["drivers"], [{"driver_item": "PS-300W-3x100", "qty": 1}])
		outputs = check(self, plan, [TRIPLE])[1]["outputs"]
		self.assertEqual(sorted(outputs.values()), [60, 80])

	def test_grouping_respects_the_total_supply_limit(self):
		total = supply("PS-150W-2x100", 150, 100, 2)  # 120 W usable in all, 80 W per output.
		plan = plan_power(circuits(70, 40, 30), [total], allocation=GROUPED)
		self.assertEqual(plan["drivers"], [{"driver_item": "PS-150W-2x100", "qty": 2}])
		check(self, plan, [total])

	def test_a_run_too_large_for_any_output_is_still_refused(self):
		with self.assertRaisesRegex(ValueError, "No compatible supply allocation"):
			plan_power(circuits(90), [TRIPLE, SMALL], allocation=GROUPED)

	def test_grouping_prefers_the_smaller_supply_footprint(self):
		cheap_big = supply("PS-BIG", 300, 300, 1, cost=10)
		plan = plan_power(circuits(5, 5), [cheap_big, SMALL], allocation=GROUPED)
		self.assertEqual(plan["drivers"], [{"driver_item": "PS-30W", "qty": 1}])

	def test_grouping_never_needs_more_supplies_and_is_exact(self):
		rng = random.Random(7)
		for _ in range(60):
			loads = [rng.choice([3, 5, 12, 20, 33, 47, 60, 75]) for _ in range(rng.randint(1, 6))]
			per_run = plan_power(circuits(*loads), CATALOG)
			grouped = plan_power(circuits(*loads), CATALOG, allocation=GROUPED)
			check(self, per_run, CATALOG)
			check(self, grouped, CATALOG)
			count = sum(d["qty"] for d in grouped["drivers"])
			self.assertLessEqual(count, sum(d["qty"] for d in per_run["drivers"]))
			self.assertEqual(count, brute_force_supplies(loads, CATALOG), loads)

	def test_the_largest_supported_search_stays_fast(self):
		loads = [7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47]
		catalog = [
			supply(f"PS-{watts}-{outputs}", watts, min(watts, 100), outputs, cost=watts)
			for watts in (30, 60, 100, 150, 200, 240, 300, 320)
			for outputs in (1, 2, 3, 4)
		]
		started = time.monotonic()
		plan = plan_power(circuits(*loads), catalog, allocation=GROUPED)
		self.assertLess(time.monotonic() - started, 20)
		check(self, plan, catalog)


def brute_force_supplies(loads, candidates):
	"""Fewest supplies by exhaustive search over set partitions and output packings."""

	def fits(group, spec):
		factor = spec["usable_load_factor"]
		if sum(group) > spec["max_wattage"] * factor + 1e-9:
			return False
		cap = spec["max_wattage_per_output"] * factor
		for labels in itertools.product(range(spec["outputs_count"]), repeat=len(group)):
			sums = {}
			for label, load in zip(labels, group, strict=True):
				sums[label] = sums.get(label, 0) + load
			if all(v <= cap + 1e-9 for v in sums.values()):
				return True
		return False

	def partitions(items):
		if not items:
			yield []
			return
		first, rest = items[0], items[1:]
		for part in partitions(rest):
			for i in range(len(part)):
				yield [*part[:i], [first, *part[i]], *part[i + 1 :]]
			yield [[first], *part]

	best = None
	for part in partitions(list(loads)):
		if all(any(fits(group, spec) for spec in candidates) for group in part):
			best = len(part) if best is None else min(best, len(part))
	return best


class FamilyAdapters(unittest.TestCase):
	def test_linear_selection_passes_the_mode_and_counts_shared_outputs_once(self):
		revision = {
			"name": "PS-30W",
			"max_wattage": 30,
			"usable_load_factor": 0.8,
			"outputs_count": 1,
		}
		catalog = types.SimpleNamespace(
			candidates=MagicMock(return_value=([SMALL, TRIPLE], {"PS-30W": revision, "PS-300W-3x100": {}}))
		)
		with load_service(ROOT + ".api.tape_neon_power", {ROOT + ".api.driver_catalog": catalog}) as (
			power,
			frappe,
		):
			frappe.get_doc.return_value = Record(input_voltage="24VDC", input_protocol="PWM")
			with load_service(ROOT + ".api.linear_power", {ROOT + ".api.tape_neon_power": power}) as (
				linear,
				_,
			):
				runs = [{"run_index": i, "run_watts": 3} for i in (1, 2, 3)]
				plan, _ = linear.select("T", 3, 9, Record(tape_spec="TAPE"), runs=runs, allocation=GROUPED)
		row = plan["drivers"][0]
		self.assertEqual((row["item_code"], row["qty"], row["outputs_used"]), ("PS-30W", 1, 1))
		self.assertEqual(plan["allocation"], GROUPED)
		self.assertIn("Run 3 -> Supply 1 Output 1", row["mapping_notes"])

	def test_sheet_feeds_batch_the_grouped_mode(self):
		with load_service(ROOT + ".api.led_sheet_bundle") as (engine, _):
			feeds = circuits(*([5] * 14))
			plan = engine.plan_feeds(feeds, [SMALL], allocation=GROUPED)
			self.assertEqual(plan["allocation"], GROUPED)
			self.assertEqual(sum(d["qty"] for d in plan["drivers"]), 4)  # 12 feeds, then 2, at 4 per output.
			per_feed = engine.plan_feeds(feeds, [SMALL])
			self.assertNotIn("allocation", per_feed)
			self.assertEqual(sum(d["qty"] for d in per_feed["drivers"]), 14)

	def test_tape_and_neon_take_the_mode_off_their_selections(self):
		with load_service(ROOT + ".api.tape_neon_configurator") as (service, _):
			selections = {"cct": "30K", "power_allocation": "grouped"}
			self.assertEqual(service._power_allocation(selections, None), GROUPED)
			self.assertEqual(selections, {"cct": "30K"})
			self.assertEqual(service._power_allocation({"power_allocation": "grouped"}, "per_run"), PER_RUN)
			self.assertEqual(service._power_allocation({}, None), PER_RUN)
			with self.assertRaises(ValueError):
				service._power_allocation({}, "pooled")


class GroupedRunGroups(unittest.TestCase):
	def test_group_identity_records_only_the_grouped_mode(self):
		base = normalize(request())
		self.assertNotIn("power_allocation", base["power"])
		r = request()
		r["power"]["power_allocation"] = "per_run"
		self.assertEqual(fingerprint(normalize(r)), fingerprint(base))
		r["power"]["power_allocation"] = "grouped"
		self.assertEqual(normalize(r)["power"]["power_allocation"], GROUPED)
		self.assertNotEqual(fingerprint(normalize(r)), fingerprint(base))
		r["power"]["power_allocation"] = "pooled"
		with self.assertRaises(ValueError):
			normalize(r)
		r = request()
		r["members"][0]["input"]["segments"][0]["power_allocation"] = "grouped"
		with self.assertRaisesRegex(ValueError, "selected once for the group"):
			normalize(r)

	def test_three_small_runs_share_one_supply_output_and_price_it(self):
		def preview(_request, geometry):
			# Each run is a 3 W strip with no other components.
			return {
				"build": {"engine_version": "fixture-2", "components": [], "cables": []},
				"pricing_inputs": {},
				"circuits": circuits(3),
				"voltage": "24V",
				"output_protocol": "SW",
				"unit_msrp": 50,
			}

		catalog = types.SimpleNamespace(
			candidates=lambda *args: ([TRIPLE, SMALL], {"PS-300W-3x100": {}, "PS-30W": {}})
		)
		items = types.SimpleNamespace(
			item_row=lambda item, qty, role: {
				"item_code": item,
				"qty": qty,
				"stock_uom": "Nos",
				"uom": "Nos",
				"role": role,
			}
		)
		prices = {"PS-300W-3x100": 90, "PS-30W": 20}
		extras = {
			ROOT + ".api.driver_catalog": catalog,
			ROOT + ".api.tape_neon_build": items,
			ROOT + ".api.tape_neon_pricing": types.SimpleNamespace(
				selling_amount=lambda item, qty: prices[item] * qty
			),
		}
		with load_service(ROOT + ".api.fixture_group_configurator", extras) as (engine, frappe):
			frappe.get_doc.return_value = Record(is_active=1)
			with patch.object(engine, "_preview_member", side_effect=preview):
				per_run = engine.calculate(request())
				r = request()
				r["power"]["power_allocation"] = "grouped"
				grouped = engine.calculate(r)
		self.assertEqual(
			per_run["build"]["power_plan"]["drivers"], [{"driver_item": "PS-300W-3x100", "qty": 1}]
		)
		plan = grouped["build"]["power_plan"]
		self.assertEqual(plan["drivers"], [{"driver_item": "PS-30W", "qty": 1}])
		self.assertEqual({(a["supply"], a["output"]) for a in plan["allocations"]}, {(1, 1)})
		power = [row for row in grouped["pricing"]["breakdown"] if row.get("role") == "power"]
		self.assertEqual(
			power, [{"item_code": "PS-30W", "role": "power", "qty": 1, "unit_msrp": 20, "extended_msrp": 20}]
		)
		self.assertEqual(grouped["pricing"]["msrp_unit"] - per_run["pricing"]["msrp_unit"], 20 - 90)
		self.assertNotEqual(grouped["config_hash"], per_run["config_hash"])
		self.assertEqual(json.loads(grouped["build_snapshot_json"])["power_plan"]["allocation"], GROUPED)


if __name__ == "__main__":
	unittest.main()
