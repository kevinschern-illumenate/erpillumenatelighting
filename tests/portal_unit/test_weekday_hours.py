import unittest
from datetime import datetime

from illumenate_lighting.illumenate_lighting.weekday_hours import add_weekday_hours


class WeekdayHours(unittest.TestCase):
	def test_hours_inside_the_week_are_plain_hours(self):
		# Monday 09:00 + 24 h = Tuesday 09:00
		self.assertEqual(add_weekday_hours(datetime(2026, 11, 23, 9), 24), datetime(2026, 11, 24, 9))

	def test_weekend_is_skipped(self):
		# Friday 16:00 + 24 h = Monday 16:00 (8 h Friday, 16 h Monday)
		self.assertEqual(add_weekday_hours(datetime(2026, 11, 27, 16), 24), datetime(2026, 11, 30, 16))

	def test_72_hours_from_thursday_lands_on_tuesday(self):
		self.assertEqual(add_weekday_hours(datetime(2026, 11, 26, 10), 72), datetime(2026, 12, 1, 10))

	def test_a_weekend_start_counts_from_monday(self):
		self.assertEqual(add_weekday_hours(datetime(2026, 11, 28, 15), 4), datetime(2026, 11, 30, 4))
		self.assertEqual(add_weekday_hours(datetime(2026, 11, 29, 23, 30), 0), datetime(2026, 11, 30))

	def test_ending_exactly_at_friday_midnight_stays_on_friday_night(self):
		self.assertEqual(add_weekday_hours(datetime(2026, 11, 27, 20), 4), datetime(2026, 11, 28))


if __name__ == "__main__":
	unittest.main()
