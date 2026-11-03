"""Hardening plan 1.1: PER_RUN mounting accessories follow the tape/neon run split."""

import unittest

from test_services import Record, load_service

MODULE = "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator"
FOOT = 304.8


class RunSplitDrivesPerRunAccessories(unittest.TestCase):
	def split(self, service, feet, watts_per_ft, voltage_drop_ft):
		return service._compute_run_split(
			tape_length_mm=feet * FOOT,
			watts_per_ft=watts_per_ft,
			voltage_drop_max_run_ft=voltage_drop_ft,
			cut_increment_mm=0,
			is_free_cutting=True,
		)

	def per_run_qty(self, service, runs, **rule):
		return service._calculate_accessory_qty(
			qty_rule_type="PER_RUN",
			qty_rule_value=rule.get("value", 1),
			min_qty=rule.get("min_qty", 0),
			rounding="CEIL",
			length_mm=0,
			runs=runs,
		)

	def test_one_two_and_n_runs_whether_watts_or_voltage_drop_limit(self):
		cases = (
			# feet, W/ft, voltage-drop ft, expected runs, limiting factor
			(10, 4.4, 32, 1, "watts"),
			(30, 4.4, 32, 2, "watts"),  # 85 W / 4.4 W/ft ≈ 19.3 ft < 32 ft
			(100, 4.4, 32, 6, "watts"),
			(12, 2.0, 16, 1, "voltage drop"),
			(30, 2.0, 16, 2, "voltage drop"),  # 16 ft < 85 W / 2 W/ft = 42.5 ft
			(50, 2.0, 16, 4, "voltage drop"),
		)
		with load_service(MODULE) as (service, _frappe):
			for feet, watts, drop, runs, limit in cases:
				with self.subTest(feet=feet, limit=limit):
					split = self.split(service, feet, watts, drop)
					self.assertEqual(split["runs_count"], runs)
					self.assertEqual(len(split["runs"]), runs)
					by_watts = split["max_run_ft_by_watts"]
					self.assertEqual(split["max_run_ft_effective"], by_watts if limit == "watts" else drop)
					self.assertEqual(self.per_run_qty(service, split["runs_count"]), runs)

	def test_minimum_quantity_still_applies(self):
		with load_service(MODULE) as (service, _frappe):
			self.assertEqual(self.per_run_qty(service, 2, min_qty=3), 3)

	def test_endpoint_uses_the_calculation_run_count(self):
		rows = [Record(accessory_item="CLIP", mounting_method="Clip", qty_rule_type="PER_RUN", qty_rule_value=1, environment_rating="")]
		with load_service(MODULE) as (service, frappe):
			frappe.db.get_value.side_effect = lambda doctype, *args, **kwargs: "TPL" if doctype == "ilL-Tape-Neon-Template" else None
			frappe.get_all.return_value = rows
			qty = lambda **kw: service.get_mounting_accessories("TPL", **kw)["accessories"][0]["qty_recommended"]  # noqa: E731
			self.assertEqual(qty(runs_count="4"), 4)  # Frappe form string
			self.assertEqual(qty(runs_count=2), 2)
			self.assertEqual(qty(), 1)  # Older callers keep the one-run answer.
			self.assertEqual(qty(runs_count="not a number"), 1)
			self.assertEqual(qty(runs_count="0"), 1)


if __name__ == "__main__":
	unittest.main()
