"""Compare in-memory document values with their stored versions.

Frappe keeps Date/Datetime values exactly as assigned: a Desk form submit or
``frappe.utils.now()`` leaves a string, while ``get_doc_before_save()`` reloads
the row as ``date``/``datetime``. A plain ``!=`` then reports a change that never
happened, so immutability guards compare through ``same``.
"""

import datetime


def _as_datetime(value):
	if isinstance(value, datetime.datetime):
		return value
	if isinstance(value, datetime.date):
		return datetime.datetime.combine(value, datetime.time())
	if isinstance(value, str):
		try:
			return datetime.datetime.fromisoformat(value)
		except ValueError:
			return value
	return value


def same(a, b):
	"""Whether two field values are equal once blank and date/time representations are normalized."""
	if a in (None, "") and b in (None, ""):
		return True
	if isinstance(a, datetime.date) or isinstance(b, datetime.date):
		return _as_datetime(a) == _as_datetime(b)
	return a == b
