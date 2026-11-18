"""Build points (Schedule Wizard difficulty metric): counting rules and scoring."""

import json
import unittest
from unittest.mock import patch

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".api.build_points"


def counts(**values):
	base = {
		"runs_2c": 0,
		"runs_3c": 0,
		"runs_4c": 0,
		"runs_5c": 0,
		"runs_6c": 0,
		"loose": 0,
		"wet": 0,
		"fmc": 0,
		"assembly": 0,
	}
	base.update(values)
	return base


class WorkbookScores(unittest.TestCase):
	"""Rows from the warehouse Schedule Wizard; CapFinal must match exactly."""

	def test_rows_match_capfinal(self):
		with load_service(MODULE) as (bp, _):
			cases = [
				(counts(runs_2c=23, wet=92, fmc=69), 322),  # SO 67312
				(counts(runs_2c=25, fmc=75), 175),  # SO 68793
				(counts(runs_2c=40, assembly=40), 140),  # SO 68221
				(counts(runs_2c=169, wet=12), 190),  # SO 68101
				(counts(runs_2c=4, runs_5c=8, fmc=8), 32),  # SO 68790
				(counts(loose=12), 9),  # SO 68119
			]
			for row, expected in cases:
				self.assertAlmostEqual(bp.score(row), expected)

	def test_four_conductor_weight(self):
		with load_service(MODULE) as (bp, _):
			self.assertAlmostEqual(bp.score(counts(runs_3c=10, runs_4c=10, runs_6c=4)), 13 + 14 + 7)


class Conductors(unittest.TestCase):
	def test_channels_plus_common(self):
		with load_service(MODULE) as (bp, _):
			self.assertEqual([bp.conductor_count(c)[0] for c in (1, 2, 3, 4, 5)], [2, 3, 4, 5, 6])

	def test_spectrum_fallback_pixel_and_unknown(self):
		with load_service(MODULE) as (bp, _):
			self.assertEqual(bp.conductor_count(None, "Tunable White"), (3, None))
			self.assertEqual(bp.conductor_count(None, "RGBW"), (5, None))
			self.assertEqual(bp.conductor_count(3, "RGB", True, 4), (4, None))
			count, warning = bp.conductor_count(None, None)
			self.assertEqual(count, 2)
			self.assertIn("unknown", warning)
			self.assertEqual(bp.conductor_count(8)[0], 6)

	def test_led_conductors_follows_offering_to_package(self):
		with load_service(MODULE) as (bp, frappe):
			frappe.db.get_singles_dict.return_value = {}

			def value(doctype, name, fields, as_dict=False):
				return {
					"ilL-Rel-Tape Offering": Record(led_package="TW-PKG", tape_spec="SPEC"),
					"ilL-Attribute-LED Package": Record(channels=2, spectrum_type="Tunable White", is_pixel=0),
				}.get(doctype)

			frappe.db.get_value.side_effect = value
			self.assertEqual(bp.led_conductors(tape_offering="OFF-1"), (3, None))


class RunCounting(unittest.TestCase):
	def test_tape_chain_jumpers_and_split_runs(self):
		with load_service(MODULE) as (bp, _):
			segments = [
				{"end_type": "Jumper", "ip_rating": "IP67"},
				{"end_type": "Endcap", "ip_rating": "IP67"},  # fed by the jumper
				{"end_type": "Endcap", "ip_rating": "IP20", "runs_count": 2},  # own feed + 1 extra
			]
			runs, fmc = bp.tape_runs(segments, 3, lambda s: s["ip_rating"] == "IP67")
			self.assertEqual(fmc, 1)
			self.assertEqual(runs, [(3, True), (3, False), (3, False)])

	def test_linear_manifest_roles(self):
		with load_service(MODULE) as (bp, _):
			cables = [
				{"role": "leader"},
				{"role": "additional feed"},
				{"role": "jumper"},
				{"role": "jumper"},
				{"role": "end leader"},
			]
			self.assertEqual(bp.linear_runs(cables, 2, True), ([(2, True), (2, True)], 2))

	def test_wet_counts_per_run(self):
		with load_service(MODULE) as (bp, _):
			result = bp.tally([(2, True), (2, True), (5, False)], fmc=1, assembly=1)
			self.assertEqual(result, counts(runs_2c=2, runs_5c=1, wet=2, fmc=1, assembly=1))


class Profiles(unittest.TestCase):
	def test_assembled_wet_linear_fixture(self):
		with load_service(MODULE) as (bp, _):
			fixture = Record(
				tape_offering="OFF",
				environment_rating="Wet",
				assembly_mode="ASSEMBLED",
				cable_manifest_json=json.dumps(
					[{"role": "leader"}, {"role": "additional feed"}, {"role": "jumper"}]
				),
			)
			with patch.object(bp, "led_conductors", return_value=(2, None)), patch.object(
				bp, "is_wet", return_value=True
			):
				result = bp.fixture_profile(fixture)
			self.assertEqual(result["counts"], counts(runs_2c=2, wet=2, fmc=1, assembly=1))
			self.assertEqual(bp.score(result["counts"]), 2 + 3.5 + 2 + 2.5)

	def test_ship_pieces_fixture_is_not_assembly(self):
		with load_service(MODULE) as (bp, _):
			fixture = Record(assembly_mode="SHIP_PIECES", cable_manifest_json='[{"role": "leader"}]')
			with patch.object(bp, "led_conductors", return_value=(3, None)), patch.object(
				bp, "is_wet", return_value=False
			):
				self.assertEqual(bp.fixture_profile(fixture)["counts"], counts(runs_3c=1))

	def test_bulk_reel_is_the_only_loose(self):
		with load_service(MODULE) as (bp, _):
			reel = bp.tape_neon_profile(Record(assembly_mode="BULK_REEL"))
			self.assertEqual(reel["counts"], counts(loose=1))
			tape = Record(
				assembly_mode="SHIP_PIECES",
				build_snapshot_json=json.dumps({"computed": {"segments": [{"end_type": "Endcap"}]}}),
			)
			with patch.object(bp, "led_conductors", return_value=(2, None)), patch.object(
				bp, "is_wet", return_value=False
			):
				self.assertEqual(bp.tape_neon_profile(tape)["counts"], counts(runs_2c=1))

	def test_unknown_conductors_warn(self):
		with load_service(MODULE) as (bp, _):
			fixture = Record(cable_manifest_json='[{"role": "leader"}]')
			with patch.object(bp, "led_conductors", return_value=(2, "Conductor count unknown")), patch.object(
				bp, "is_wet", return_value=False
			):
				self.assertEqual(bp.fixture_profile(fixture)["warnings"], ["Conductor count unknown"])


class SettingsAndOrders(unittest.TestCase):
	def test_weights_and_capacity_from_settings(self):
		with load_service(MODULE) as (bp, _):
			values = {"weight_wet": "2", "weight_fmc": "", "points_per_person_day": "57.5"}
			weights = bp.weights(values)
			self.assertEqual(weights["wet"], 2.0)
			self.assertEqual(weights["fmc"], 2.0)
			self.assertEqual(weights["runs_4c"], 1.4)
			self.assertAlmostEqual(bp.points_per_hour(values), 57.5 / 8.5)

	def test_order_totals_multiply_by_quantity(self):
		with load_service(MODULE) as (bp, _):
			order = Record(
				net_total=10000,
				total_commission=2000,
				items=[
					Record(name="r1", idx=1, item_code="FIX", qty=3, stock_qty=3, ill_bom="BOM-FIX"),
					Record(name="r2", idx=2, item_code="DRIVER", qty=5, stock_qty=5),
				],
			)
			per_unit = {"BOM-FIX": counts(runs_2c=1, wet=1, assembly=1) | {"warnings": []}}
			with patch.object(bp, "line_bom", side_effect=lambda row: row.get("ill_bom")), patch.object(
				bp, "bom_counts", side_effect=lambda bom: per_unit.get(bom)
			):
				lines, total = bp.order_totals(order, values={})
			self.assertEqual(lines["r1"]["points"], 3 * (1 + 1.75 + 2.5))
			self.assertEqual(lines["r2"]["points"], 0)
			self.assertEqual(total["assembly"], 3)
			self.assertAlmostEqual(total["points"], 15.75)
			self.assertAlmostEqual(total["worth_per_point"], round(8000 / 15.75, 2))
			self.assertAlmostEqual(total["hours"], round(15.75 / (57.5 / 8.5), 2))

	def test_floor_adjustments_add_to_counted_totals(self):
		with load_service(MODULE) as (bp, _):
			order = Record(
				net_total=0,
				ill_build_points_adjustments=json.dumps({"runs_3c": 2, "runs_2c": -5, "bogus": 9, "fmc": 0}),
				items=[Record(name="r1", idx=1, item_code="FIX", qty=3, stock_qty=3, ill_bom="BOM-FIX")],
			)
			per_unit = {"BOM-FIX": counts(runs_2c=1) | {"warnings": []}}
			with patch.object(bp, "line_bom", side_effect=lambda row: row.get("ill_bom")), patch.object(
				bp, "bom_counts", side_effect=lambda bom: per_unit.get(bom)
			):
				lines, total = bp.order_totals(order, values={})
			self.assertEqual(total["computed"]["runs_2c"], 3)
			self.assertEqual(total["adjustments"], {"runs_2c": -5.0, "runs_3c": 2.0})
			self.assertEqual(total["runs_2c"], 0)  # never below zero
			self.assertEqual(total["runs_3c"], 2)
			self.assertAlmostEqual(total["points"], 2 * 1.3)
			self.assertEqual(lines["r1"]["runs_2c"], 3)  # lines stay as counted

	def test_adjustments_ignore_bad_values(self):
		with load_service(MODULE) as (bp, _):
			self.assertEqual(bp.adjustments(None), {})
			self.assertEqual(bp.adjustments("not json"), {})
			self.assertEqual(bp.adjustments('{"wet": "x", "loose": "1.5"}'), {"loose": 1.5})


if __name__ == "__main__":
	unittest.main()
