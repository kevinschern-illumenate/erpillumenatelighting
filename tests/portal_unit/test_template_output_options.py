"""Output Options on the fixture template (owner, 2026-11-18)."""

import unittest

from test_services import ROOT, load_service

LEVELS = [
	{"name": f"{v} lm/ft", "value": v} for v in (50, 100, 200, 250, 300, 400, 500, 750, 1000, 1250, 1500)
]
# (lumens per foot, only lens, watts per foot, max run length) like ILL-SH01-SW's tapes.
TAPES = [
	(100, None, 0.8, 45),
	(200, None, 1.7, 35),
	(300, None, 2.5, 28),
	(500, None, 4.0, 20),
	(1000, None, 8.5, 10),
]
LENSES = [("White", 0.56), ("Frosted", 0.98), ("Clear", 0.99), ("Black", 0.32)]


class OutputOptions(unittest.TestCase):
	def module(self):
		context = load_service(ROOT + ".template_output_options")
		module, _frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		return module

	def grid(self, rows):
		result = {}
		for row in rows:
			result.setdefault(row["lens_group"], {})[row["output_level"]] = (
				row["fixture_wattage"],
				row["max_run_length"],
			)
		return result

	def test_each_lens_uses_the_tape_that_makes_the_output(self):
		grid = self.grid(self.module().table(LENSES, TAPES, LEVELS))
		# White at 100 lm/ft is the 200 lm/ft tape; Black the 300; Frosted and Clear the 100.
		self.assertEqual(grid["White Lens"]["100 lm/ft"], ("1.7W", "35ft"))
		self.assertEqual(grid["Black Lens"]["100 lm/ft"], ("2.5W", "28ft"))
		self.assertEqual(grid["Other Lenses"]["100 lm/ft"], ("0.8W", "45ft"))
		# A lens that does not reach an output shows dashes.
		self.assertEqual(grid["Black Lens"]["1000 lm/ft"], ("—", "—"))

	def test_max_footage_per_100w_is_80w_over_the_wattage_rounded_up(self):
		rows = self.module().table(LENSES, TAPES, LEVELS)
		per_100w = {(r["lens_group"], r["output_level"]): r["max_footage_100w"] for r in rows}
		self.assertEqual(per_100w[("White Lens", "100 lm/ft")], "48ft")  # 80 / 1.7 = 47.06
		self.assertEqual(per_100w[("Other Lenses", "100 lm/ft")], "100ft")  # 80 / 0.8 = 100
		self.assertEqual(per_100w[("Black Lens", "1000 lm/ft")], "—")

	def test_lenses_with_the_same_numbers_share_a_group_and_singles_come_first(self):
		rows = self.module().table(LENSES, TAPES, LEVELS)
		groups = list(dict.fromkeys(row["lens_group"] for row in rows))
		self.assertEqual(groups, ["White Lens", "Black Lens", "Other Lenses"])
		# Only levels some lens reaches, lowest first.
		levels = list(dict.fromkeys(row["output_level"] for row in rows))
		self.assertEqual(levels[0], "50 lm/ft")
		self.assertNotIn("1250 lm/ft", levels)

	def test_two_shared_groups_are_named_by_their_lenses(self):
		lenses = [("White", 0.5), ("Frosted", 0.5), ("Clear", 1.0), ("Black", 1.0)]
		groups = {row["lens_group"] for row in self.module().table(lenses, TAPES, LEVELS)}
		self.assertEqual(groups, {"White & Frosted Lenses", "Clear & Black Lenses"})

	def test_the_highest_wattage_and_shortest_run_of_equal_tapes(self):
		tapes = [(100, None, 0.8, 45), (100, None, 0.9, 40)]
		rows = self.module().table([("Clear", 1.0)], tapes, LEVELS)
		self.assertEqual(
			rows,
			[
				{
					"lens_group": "Clear Lens",
					"output_level": "100 lm/ft",
					"fixture_wattage": "0.9W",
					"max_run_length": "40ft",
					"max_footage_100w": "89ft",
				}
			],
		)

	def test_an_offering_limited_to_a_lens_counts_for_that_lens_only(self):
		tapes = [(100, None, 0.8, 45), (1500, "Clear", 14.4, 7)]
		grid = self.grid(self.module().table([("White", 0.56), ("Clear", 1.0)], tapes, LEVELS))
		self.assertEqual(grid["Clear Lens"]["1500 lm/ft"], ("14.4W", "7ft"))
		self.assertEqual(grid["White Lens"]["1500 lm/ft"], ("—", "—"))

	def test_nothing_without_lenses_or_levels(self):
		module = self.module()
		self.assertEqual(module.table([], TAPES, LEVELS), [])
		self.assertEqual(module.table(LENSES, TAPES, []), [])



class NeonOutputOptions(unittest.TestCase):
	"""LED Neon (owner, 2026-11-19): one unnamed group, the template's own outputs as columns."""

	def module(self):
		context = load_service(ROOT + ".template_output_options")
		module, _frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		return module

	def test_each_output_takes_the_nearest_tape_spec(self):
		rows = self.module().neon_table(
			[{"name": "300 lm/ft", "value": 300}, {"name": "150 lm/ft", "value": 150}],
			[(148, 2.74, 16.4), (305, 5.1, 9), (None, 9, 1)],
		)
		self.assertEqual(
			rows,
			[
				{
					"lens_group": "",
					"output_level": "150 lm/ft",
					"fixture_wattage": "2.7W",
					"max_run_length": "16.4ft",
					"max_footage_100w": "30ft",
				},
				{
					"lens_group": "",
					"output_level": "300 lm/ft",
					"fixture_wattage": "5.1W",
					"max_run_length": "9ft",
					"max_footage_100w": "16ft",
				},
			],
		)

	def test_no_tape_lumens_gives_dashes(self):
		rows = self.module().neon_table([{"name": "150 lm/ft", "value": 150}], [(None, 2.7, 16)])
		self.assertEqual(rows[0]["fixture_wattage"], "—")


if __name__ == "__main__":
	unittest.main()
