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


def fixture_groups_enabled():
	"""Independent fixture groups (multi-run lines). On unless a site sets the flag false."""
	return conf_flag("ill_portal_fixture_groups", default=True)


def hero_image_first_enabled():
	"""D1 image order (template hero image first, plan 5.4). Off restores gallery-first."""
	return conf_flag("ill_portal_hero_image_first", default=True)


def media_derivatives_enabled():
	"""WebP derivatives for staff product images (plan 5.8). On unless a site sets the flag false."""
	return conf_flag("ill_media_derivatives", default=True)


def webflow_image_derivatives_enabled():
	"""Add ``image_derivatives`` to Webflow payloads (plan 5.8). Off by default: the payload
	contract changes, so n8n must accept the key before a site turns this on."""
	return conf_flag("ill_webflow_image_derivatives", default=False)


def sheet_server_options_enabled():
	"""Server-checked LED Sheet option cascade (plan 6.4). Off leaves the browser matcher alone."""
	return conf_flag("ill_portal_sheet_server_options", default=True)


def option_projection_cache_enabled():
	"""Cache configurator option projections per catalog revision (plan 6.5). Off reads live every time."""
	return conf_flag("ill_option_projection_cache", default=True)


def build_preview_enabled():
	"""Read-only SVG preview of the calculated build in the configurator review (plan 6.6)."""
	return conf_flag("ill_portal_build_preview", default=True)


def configuration_compare_enabled():
	"""Side-by-side comparison of two saved schedule lines (plan 6.7)."""
	return conf_flag("ill_portal_configuration_compare", default=True)


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
