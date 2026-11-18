"""Build operation time on Work Orders and weight calibration from labour time."""

import random
import unittest
from unittest.mock import patch

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".api.build_operations"
KEYS = ("runs_2c", "runs_3c", "runs_4c", "runs_5c", "runs_6c", "loose", "wet", "fmc", "assembly")
SETTINGS = {"points_per_person_day": 57.5, "paid_hours_per_day": 8.5}


def synthetic(true_minutes, n=60, seed=7):
	"""Work Orders whose labour time is exactly the sum of true per-unit minutes."""
	rng = random.Random(seed)
	rows = []
	for _ in range(n):
		counts = {k: 0 for k in KEYS}
		counts[rng.choice(KEYS[:5])] = rng.randint(1, 30)
		for k in ("wet", "fmc", "assembly", "loose"):
			if rng.random() < 0.5:
				counts[k] = rng.randint(1, 20)
		rows.append((counts, sum(counts[k] * true_minutes[k] for k in KEYS)))
	return rows


class Maths(unittest.TestCase):
	def test_solve(self):
		with load_service(MODULE) as (bo, _):
			x, y = bo.solve([[2, 1], [1, 3]], [3, 5])
			self.assertAlmostEqual(x, 0.8)
			self.assertAlmostEqual(y, 1.4)
			self.assertIsNone(bo.solve([[1, 2], [2, 4]], [1, 2]))

	def test_minutes_per_point(self):
		with load_service(MODULE) as (bo, _):
			self.assertAlmostEqual(bo.minutes_per_point(SETTINGS), 60 / (57.5 / 8.5))

	def test_fit_recovers_true_minutes(self):
		with load_service(MODULE) as (bo, _):
			true = {"runs_2c": 9, "runs_3c": 12, "runs_4c": 13, "runs_5c": 14, "runs_6c": 16, "loose": 5, "wet": 20, "fmc": 15, "assembly": 30}
			prior = {k: 10 for k in KEYS}
			fitted = bo.fit(synthetic(true), prior, ridge=0.001)
			for k in KEYS:
				self.assertAlmostEqual(fitted[k], true[k], delta=true[k] * 0.05, msg=k)

	def test_suggest_relative_to_2c_and_keeps_rare_factors(self):
		with load_service(MODULE) as (bo, _):
			# Wet runs actually take 3x a 2C run (weight 3, not 1.75); no 6C examples at all.
			true = {"runs_2c": 9, "runs_3c": 11.7, "runs_4c": 12.6, "runs_5c": 13.5, "runs_6c": 15.75, "loose": 6.75, "wet": 27, "fmc": 18, "assembly": 22.5}
			data = [(c, m) for c, m in synthetic(true, n=120) if not c["runs_6c"]]
			with patch.object(bo, "RIDGE", 0.001):
				result = bo.suggest(data, SETTINGS)
			self.assertEqual(result["samples"], len(data))
			self.assertEqual(result["suggested_weights"]["runs_2c"], 1)
			self.assertAlmostEqual(result["suggested_weights"]["wet"], 3, delta=0.25)
			self.assertEqual(result["support"]["runs_6c"], 0)
			self.assertEqual(result["suggested_weights"]["runs_6c"], 1.75)  # kept: no evidence
			# 9 minutes per 2C point over an 8.5 h day = 56.67 points per person-day.
			self.assertAlmostEqual(result["suggested_points_per_person_day"], 8.5 * 60 / 9, delta=2)

	def test_too_few_samples_keeps_everything(self):
		with load_service(MODULE) as (bo, _):
			data = [({**{k: 0 for k in KEYS}, "runs_2c": 2}, 20)] * 3
			result = bo.suggest(data, SETTINGS)
			self.assertEqual(result["suggested_weights"]["runs_2c"], 1.0)
			self.assertEqual(result["observed_minutes_per_point"], 10)
			self.assertEqual(result["observed_points_per_person_day"], 51)


class Operation(unittest.TestCase):
	def _doc(self, points, operations=()):
		doc = Record(ill_build_points=points, operations=list(operations))
		doc.append = lambda table, row: doc[table].append(row)
		return doc

	def test_added_only_when_enabled(self):
		with load_service(MODULE) as (bo, _):
			on = {**SETTINGS, "add_build_operation": 1, "build_operation": "Build", "build_workstation": "Production Floor"}
			with patch.object(bo.build_points, "settings", return_value=on):
				doc = self._doc(57.5)
				bo.add_build_operation(doc)
				(row,) = doc.operations
				self.assertEqual((row["operation"], row["workstation"]), ("Build", "Production Floor"))
				self.assertAlmostEqual(row["time_in_mins"], 510)  # one person-day of points = 8.5 h
				kept = self._doc(10, [{"operation": "Custom"}])
				bo.add_build_operation(kept)
				self.assertEqual(len(kept.operations), 1)
				zero = self._doc(0)
				bo.add_build_operation(zero)
				self.assertEqual(zero.operations, [])
			with patch.object(bo.build_points, "settings", return_value={**on, "add_build_operation": 0}):
				off = self._doc(10)
				bo.add_build_operation(off)
				self.assertEqual(off.operations, [])


class Samples(unittest.TestCase):
	def test_entered_minutes_win_over_job_cards(self):
		with load_service(MODULE) as (bo, _):
			orders = [
				Record(name="WO-1", sales_order="SO-1", production_item="I", item_name="Fixture", qty=2, produced_qty=2, bom_no="B", ill_actual_build_minutes=90),
				Record(name="WO-2", sales_order="SO-2", production_item="I", item_name="Fixture", qty=1, produced_qty=1, bom_no="B"),
				Record(name="WO-3", sales_order="SO-3", production_item="I", item_name="Fixture", qty=1, produced_qty=1, bom_no="B"),
			]
			per_unit = {k: 0 for k in KEYS} | {"runs_2c": 3, "wet": 1}
			with patch.object(bo, "completed_work_orders", return_value=orders), patch.object(
				bo, "job_card_minutes", return_value={"WO-1": 500, "WO-2": 40}
			), patch.object(bo.build_points, "bom_counts", return_value=per_unit):
				rows = bo.samples("2026-11-01", "2026-11-30", SETTINGS)
			self.assertEqual([(r["minutes"], r["source"]) for r in rows], [(90, "Entered"), (40, "Job Card"), (0, "No time")])
			self.assertEqual(rows[0]["runs_2c"], 6)
			self.assertAlmostEqual(rows[0]["points"], 2 * (3 + 1.75))
			self.assertAlmostEqual(rows[0]["minutes_per_point"], round(90 / 9.5, 2))


if __name__ == "__main__":
	unittest.main()
