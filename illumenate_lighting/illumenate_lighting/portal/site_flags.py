"""Read optional ilL site-config keys the way Frappe Cloud may store them.

Frappe Cloud's Site Config keys are typed (String, Boolean, JSON, Number), so the
same setting can arrive as ``False``, ``0``, ``"false"`` or a JSON-encoded string.
An unreadable value is logged once per process and treated as absent, so one bad
key cannot break every request.
"""

import json

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import parse_bool

_reported = set()


def conf_flag(key, default=False):
	"""A Boolean flag: true/false, 1/0 or their string forms. Absent or invalid → default."""
	value = frappe.conf.get(key)
	try:
		return parse_bool(value, default=default)
	except ValueError:
		_report(key, value, "a boolean (true/false)")
		return default


def conf_list(key):
	"""A list of strings, stored as JSON or a JSON-encoded string. Absent or invalid → None."""
	value = frappe.conf.get(key)
	if value is None:
		return None
	parsed = value
	if isinstance(parsed, str):
		try:
			parsed = json.loads(parsed)
		except ValueError:
			parsed = None
	if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
		_report(key, value, "a JSON list of strings")
		return None
	return parsed


def _report(key, value, expected):
	marker = (key, repr(value))
	if marker in _reported:
		return
	_reported.add(marker)
	frappe.log_error(
		title=f"Invalid site config: {key}",
		message=f"{key} should be {expected}; got {value!r}. It is being treated as absent.",
	)
