# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Deadlines that count working hours only: weekends and holidays never use up time."""

from datetime import date, datetime, time, timedelta


def add_weekday_hours(start: datetime, hours: float, holidays=()) -> datetime:
	"""``start`` plus ``hours``, skipping Saturdays, Sundays and any date in ``holidays``.

	A start on a day off counts from the next working day at 00:00. Friday 16:00 plus 24 hours is
	Monday 16:00, or Tuesday 16:00 when Monday is a holiday.
	"""
	days_off = {_as_date(value) for value in holidays or ()}
	remaining = timedelta(hours=hours)
	current = start
	while True:
		if current.weekday() >= 5 or current.date() in days_off:
			current = datetime.combine(current.date() + timedelta(days=1), time.min)
			continue
		midnight = datetime.combine(current.date() + timedelta(days=1), time.min)
		if remaining <= midnight - current:
			return current + remaining
		remaining -= midnight - current
		current = midnight


def _as_date(value):
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	return date.fromisoformat(str(value)[:10])
