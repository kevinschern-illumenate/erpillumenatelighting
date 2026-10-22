"""Equal-length run splitting: the fewest equal runs instead of full runs then a remainder."""

import copy
import unittest

from test_fixture_groups import request as group_request
from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.group_contract import normalize

MM_PER_FOOT = 304.8
# Two-inch cut points, so 10 ft and 15 ft both land exactly on a cut.
CUT_MM = 50.8


def equal_run_lengths(*args):
	with load_service(ROOT + ".api.linear_power") as (module, _frappe):
		return module.equal_run_lengths(*args)


class EqualRunLengths(unittest.TestCase):
	def test_twenty_feet_at_a_fifteen_foot_limit_is_two_ten_foot_runs(self):
		lengths = equal_run_lengths(20 * MM_PER_FOOT, 15 * MM_PER_FOOT, CUT_MM)
		self.assertEqual(len(lengths), 2)
		for length in lengths:
			self.assertAlmostEqual(length, 10 * MM_PER_FOOT)

	def test_a_run_that_fits_is_left_whole(self):
		self.assertEqual(equal_run_lengths(3000, 4572, 50), [3000])
		self.assertEqual(equal_run_lengths(3000, float("inf"), 50), [3000])
		self.assertEqual(equal_run_lengths(0, 4572, 50), [])

	def test_runs_end_on_cut_points_and_differ_by_at_most_one_cut(self):
		lengths = equal_run_lengths(6050, 4572, 50)
		self.assertEqual(lengths, [3050, 3000])

	def test_every_split_fits_the_limit_and_keeps_the_total(self):
		for cut in (25, 33.33, 50, 55.5, 100):
			for limit in (900, 1524, 2438.4, 4572):
				for units in range(1, 400, 7):
					total = units * cut
					lengths = equal_run_lengths(total, limit, cut)
					self.assertAlmostEqual(sum(lengths), total, places=6)
					self.assertLessEqual(max(lengths), limit + 1e-6)
					self.assertLessEqual(max(lengths) - min(lengths), cut + 1e-6)
					# Never more runs than the cut points force.
					self.assertEqual(
						len(lengths), -(-units // int(limit // cut + 1e-9)) if total > limit else 1
					)

	def test_tape_off_its_cut_points_is_split_evenly(self):
		lengths = equal_run_lengths(6001, 4572, 50)
		self.assertEqual(len(lengths), 2)
		self.assertAlmostEqual(lengths[0], 3000.5)
		self.assertAlmostEqual(sum(lengths), 6001)


def engine():
	return load_service(ROOT + ".api.configurator_engine")


def tape_docs(frappe, watts_per_foot):
	spec = Record(cut_increment_mm=CUT_MM, watts_per_foot=watts_per_foot, voltage_drop_max_run_length_ft=None)
	frappe.get_doc.side_effect = lambda doctype, name=None: spec
	frappe.db.exists.return_value = False
	frappe.db.get_value.return_value = None
	frappe.get_all.return_value = []
	template = Record(
		leader_allowance_mm_per_fixture=15, default_profile_stock_len_mm=2000, assembled_max_len_mm=2590
	)
	offering = Record(tape_spec="TAPE", cut_increment_mm_override=None, watts_per_ft_override=None)
	return template, offering


class SingleSegmentRuns(unittest.TestCase):
	def compute(self, equal, **kwargs):
		with engine() as (module, frappe):
			template, offering = tape_docs(frappe, kwargs.pop("watts_per_foot", 4.0))
			return module._compute_manufacturable_outputs(
				"ILL-SH01-SW",
				"TAPE-OFFERING",
				kwargs.pop("length_mm"),
				None,
				None,
				"End",
				"Frosted",
				"White",
				template_doc=template,
				tape_offering_doc=offering,
				equal_length_runs=equal,
				**kwargs,
			)

	def test_default_keeps_full_runs_then_a_remainder(self):
		result = self.compute(False, length_mm=20 * MM_PER_FOOT + 40, override_max_run_ft=15)
		self.assertEqual([run["run_len_mm"] for run in result["runs"]], [4572, 1524])
		self.assertNotIn("equal_length_runs", result)

	def test_equal_runs_split_twenty_feet_into_two_ten_foot_runs(self):
		default = self.compute(False, length_mm=20 * MM_PER_FOOT + 40, override_max_run_ft=15)
		result = self.compute(True, length_mm=20 * MM_PER_FOOT + 40, override_max_run_ft=15)
		self.assertEqual(result["runs_count"], 2)
		self.assertEqual(result["leader_qty"], 2)
		self.assertEqual([run["run_len_mm"] for run in result["runs"]], [3048, 3048])
		self.assertEqual([run["run_index"] for run in result["runs"]], [1, 2])
		self.assertTrue(result["equal_length_runs"])
		# Same tape, same watts: only how it is split changes.
		self.assertEqual(result["tape_cut_length_mm"], default["tape_cut_length_mm"])
		self.assertAlmostEqual(result["total_watts"], default["total_watts"], places=1)

	def test_equal_runs_respect_the_supply_output_watt_limit(self):
		# 15.75 ft of 6.4 W/ft tape on supplies that carry 80 W per output.
		result = self.compute(True, length_mm=4851, watts_per_foot=6.4, max_watts_per_run=80)
		self.assertEqual(result["runs_count"], 2)
		self.assertTrue(all(run["run_watts"] <= 80 for run in result["runs"]))
		watts = [run["run_watts"] for run in result["runs"]]
		self.assertLess(max(watts) - min(watts), 1.1)

	def test_a_run_that_fits_is_unchanged(self):
		default = self.compute(False, length_mm=2000, override_max_run_ft=15)
		result = self.compute(True, length_mm=2000, override_max_run_ft=15)
		self.assertEqual(result["runs"], default["runs"])


class MultiSegmentRuns(unittest.TestCase):
	def compute(self, equal, segments, **kwargs):
		with engine() as (module, frappe):
			template, offering = tape_docs(frappe, 4.0)
			return module._compute_multisegment_outputs(
				"ILL-SH01-SW",
				"TAPE-OFFERING",
				segments,
				"Dry",
				"White",
				"White",
				"Frosted",
				template_doc=template,
				tape_offering_doc=offering,
				equal_length_runs=equal,
				**kwargs,
			)

	def segments(self):
		return [
			{"requested_length_mm": 3048, "end_type": "Jumper"},
			{"requested_length_mm": 3048, "end_type": "Endcap"},
		]

	def test_default_keeps_full_runs_then_a_remainder(self):
		result = self.compute(False, self.segments(), override_max_run_ft=15)
		lengths = [run["run_len_mm"] for run in result["runs"]]
		self.assertEqual(lengths[0], 4572)
		self.assertNotIn("equal_length_runs", result)

	def test_total_tape_is_split_into_equal_runs_across_segments(self):
		default = self.compute(False, self.segments(), override_max_run_ft=15)
		result = self.compute(True, self.segments(), override_max_run_ft=15)
		lengths = [run["run_len_mm"] for run in result["runs"]]
		self.assertEqual(result["runs_count"], 2)
		self.assertEqual(result["leader_qty"], 2)
		self.assertLessEqual(max(lengths) - min(lengths), CUT_MM)
		self.assertEqual(sum(lengths), result["total_tape_length_mm"])
		self.assertAlmostEqual(result["total_watts"], default["total_watts"], places=1)
		self.assertTrue(result["equal_length_runs"])

	def test_equal_runs_respect_the_supply_output_watt_limit(self):
		result = self.compute(True, self.segments(), max_watts_per_run=30)
		self.assertTrue(all(run["run_watts"] <= 30 for run in result["runs"]))
		self.assertEqual(result["runs_count"], 3)


class GroupPolicy(unittest.TestCase):
	def test_equal_runs_join_the_group_power_policy_only_when_chosen(self):
		plain = normalize(group_request())
		self.assertNotIn("equal_length_runs", plain["power"])
		chosen = group_request()
		chosen["power"]["equal_length_runs"] = True
		self.assertTrue(normalize(chosen)["power"]["equal_length_runs"])
		unchecked = group_request()
		unchecked["power"]["equal_length_runs"] = False
		self.assertEqual(normalize(unchecked), plain)

	def test_equal_runs_are_chosen_once_for_the_group(self):
		value = group_request()
		value["members"][0]["input"]["segments"][0]["equal_length_runs"] = True
		with self.assertRaisesRegex(ValueError, "equal_length_runs"):
			normalize(copy.deepcopy(value))


if __name__ == "__main__":
	unittest.main()
