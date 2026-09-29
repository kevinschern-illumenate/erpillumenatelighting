"""The tape behind each lens is the one whose delivered output is closest to the chosen level."""

import unittest

from test_services import ROOT  # puts the app on sys.path

from illumenate_lighting.illumenate_lighting.api.tape_selection import (
	closest_tape,
	delivered_lm_ft,
	transmission_fraction,
)

# Static White HD tape outputs (lm/ft) and watts per foot from the published tape sheet.
TAPE_WATTS = {100: 0.8, 200: 1.7, 300: 2.5, 400: 3.6, 500: 4.0, 750: 6.4, 1000: 8.5, 1250: 11.6, 1500: 14.4}
FIXTURE_LEVELS = [100, 200, 250, 300, 400, 500, 750, 1000, 1250, 1500]


def column(target, transmission):
	"""Mirror the engine: tapes that round to ``target``, then the closest of them."""
	matches = [
		{"output_value_lm_ft": tape}
		for tape in TAPE_WATTS
		if min(FIXTURE_LEVELS, key=lambda level: abs(level - delivered_lm_ft(tape, transmission))) == target
	]
	chosen = closest_tape(matches, target, transmission)
	return TAPE_WATTS[chosen["output_value_lm_ft"]] if chosen else None


class TapeSelection(unittest.TestCase):
	def test_transmission_accepts_fraction_or_percent(self):
		self.assertEqual(transmission_fraction(0.56), 0.56)
		self.assertEqual(transmission_fraction(56), 0.56)
		self.assertEqual(transmission_fraction(None), 1.0)
		self.assertEqual(transmission_fraction("bad"), 1.0)

	def test_reproduces_the_published_st_helens_wattages(self):
		# Output columns 100/300/500/750/1000 lm/ft; "—" is None.
		expected = {
			0.56: [1.7, 4.0, 8.5, 11.6, None],  # White lens
			0.32: [2.5, 8.5, 14.4, None, None],  # Black lens
			0.99: [0.8, 2.5, 4.0, 6.4, 8.5],  # Frosted and clear lenses
		}
		for transmission, watts in expected.items():
			with self.subTest(transmission=transmission):
				self.assertEqual([column(level, transmission) for level in (100, 300, 500, 750, 1000)], watts)

	def test_closest_not_brightest(self):
		# White 750: 1250 tape delivers 700, 1500 tape delivers 840; both round to 750.
		chosen = closest_tape([{"output_value_lm_ft": 1500}, {"output_value_lm_ft": 1250}], 750, 0.56)
		self.assertEqual(chosen["output_value_lm_ft"], 1250)

	def test_ties_prefer_the_lower_output_tape(self):
		chosen = closest_tape([{"output_value_lm_ft": 300}, {"output_value_lm_ft": 100}], 200, 1.0)
		self.assertEqual(chosen["output_value_lm_ft"], 100)

	def test_empty_candidates(self):
		self.assertIsNone(closest_tape([], 100, 0.56))


if __name__ == "__main__":
	unittest.main()
