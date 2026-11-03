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


def heic_uploads_enabled():
	"""Dealer HEIC/HEIF photo uploads, converted to JPEG. On unless a site sets the flag false."""
	return conf_flag("ill_portal_heic_uploads", default=True)


def upload_widget_enabled():
	"""The shared drag-and-drop upload widget (plan 4.1). On unless a site sets the flag false."""
	return conf_flag("ill_portal_upload_widget", default=True)


def upload_purpose_enabled():
	"""Upload purpose and caption (hardening plan 4.3). On unless a site sets the flag false."""
	return conf_flag("ill_portal_upload_purpose", default=True)


def thumbnails_enabled():
	"""Server-generated WebP thumbnails for image uploads (hardening plan 4.4)."""
	return conf_flag("ill_portal_thumbnails", default=True)


def gallery_enabled():
	"""Project and line photo galleries (hardening plan 4.5)."""
	return conf_flag("ill_portal_gallery", default=True)


def upload_duplicate_check_enabled():
	"""Warn about and skip re-uploads of bytes already on a schedule (hardening plan 4.8)."""
	return conf_flag("ill_portal_upload_duplicate_check", default=True)


def dealer_logo_enabled():
	"""Dealer logo self-service on /portal/account (hardening plan 4.6)."""
	return conf_flag("ill_portal_dealer_logo", default=True)


def staff_heic_enabled():
	"""Desk HEIC-to-JPEG conversion for product imagery (hardening plan 4.7)."""
	return conf_flag("ill_desk_heic_conversion", default=True)


def portal_client_flags():
	"""Dealer-visible kill switches the portal scripts read from ``#ill-portal-flags``."""
	return {
		"upload_widget": upload_widget_enabled(),
		"upload_purpose": upload_purpose_enabled(),
		"gallery": gallery_enabled(),
	}


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
