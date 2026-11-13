"""Delivered lumens per foot on the fixture template (owner, 2026-11-13)."""

import unittest

from test_services import ROOT, load_service

LEVELS = [
	{"name": n, "output_level_name": n, "value": v}
	for n, v in (
		("50lm/ft", 50),
		("100 lm/ft", 100),
		("200 lm/ft", 200),
		("250 lm/ft", 250),
		("300 lm/ft", 300),
		("400 lm/ft", 400),
		("500 lm/ft", 500),
		("750 lm/ft", 750),
		("1000 lm/ft", 1000),
		("1250 lm/ft", 1250),
		("1500 lm/ft", 1500),
	)
]
TAPES = [(lumens, None) for lumens in (100, 200, 300, 400, 500, 750, 1000, 1250, 1500)]


class DeliveredLumens(unittest.TestCase):
	def module(self):
		context = load_service(ROOT + ".template_delivered_lumens")
		module, _frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		return module

	def test_each_tape_goes_to_its_nearest_level_and_the_nearer_wins(self):
		module = self.module()
		rows = module.table({"white": ("White", 0.56)}, TAPES, LEVELS)
		self.assertEqual(
			[(row["output_level"], row["white"]) for row in rows],
			[
				("50lm/ft", "56"),
				("100 lm/ft", "112"),
				("200 lm/ft", "224"),  # 224 beats 168 (from the 300 tape) for 200
				("300 lm/ft", "280"),
				("400 lm/ft", "420"),
				("500 lm/ft", "560"),
				("750 lm/ft", "700"),  # 700 beats 840 for 750; nothing above
			],
		)

	def test_lenses_are_columns_and_unreached_cells_stay_empty(self):
		module = self.module()
		rows = module.table(
			{"white": ("White", 0.56), "black": ("Black", 0.32)},
			[(100, None), (200, None), (1500, "White")],
			LEVELS,
		)
		by_level = {row["output_level"]: row for row in rows}
		self.assertEqual(by_level["50lm/ft"], {"output_level": "50lm/ft", "white": "56", "black": "64"})
		# The 1500 tape is limited to White: Black does not reach 750, so a dash, never 0.
		self.assertEqual(by_level["750 lm/ft"]["black"], "\u2014")
		# Only the template's lenses are columns.
		self.assertEqual(set(by_level["50lm/ft"]), {"output_level", "white", "black"})
		self.assertEqual(module.table({"white": ("White", 0.56)}, [(226.07, None)], LEVELS)[0]["white"], "126.6")
		self.assertNotIn("1000 lm/ft", by_level)

	def test_only_per_foot_levels_count(self):
		module = self.module()
		self.assertTrue(module.per_foot({"output_level_name": "50lm/ft"}))
		self.assertTrue(module.per_foot({"output_level_name": "500 lm/ft"}))
		self.assertFalse(module.per_foot({"output_level_name": "550 lm / sqft"}))
		self.assertEqual(module.transmission_fraction(56), 0.56)
		self.assertEqual(module.transmission_fraction(0.56), 0.56)
		self.assertEqual(module.transmission_fraction(None), 1.0)


if __name__ == "__main__":
	unittest.main()
