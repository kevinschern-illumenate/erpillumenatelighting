# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Deadlines that count weekday hours only: Saturday and Sunday never use up time."""

from datetime import datetime, time, timedelta


def add_weekday_hours(start: datetime, hours: float) -> datetime:
	"""``start`` plus ``hours``, skipping Saturdays and Sundays.

	A start on a weekend counts from Monday 00:00. Friday 16:00 plus 24 hours is Monday 16:00.
	"""
	remaining = timedelta(hours=hours)
	current = start
	while True:
		if current.weekday() >= 5:
			current = datetime.combine(current.date() + timedelta(days=7 - current.weekday()), time.min)
			continue
		midnight = datetime.combine(current.date() + timedelta(days=1), time.min)
		if remaining <= midnight - current:
			return current + remaining
		remaining -= midnight - current
		current = midnight
