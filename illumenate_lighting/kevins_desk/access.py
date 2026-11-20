"""Who may open Kevin's Desk.

The page and every desk endpoint answer only to the desk owner named in ilL-Desk-Settings (an enabled
System User, signed in through ERPNext's own login and 2FA). Everyone else gets "not found": a guest
is never offered a login prompt, and nobody learns the page exists.

The URL slug is random and lives in the settings record, not in the repo. It is defence in depth only;
the owner check is the real gate.
"""

import hmac
import re

import frappe

SETTINGS = "ilL-Desk-Settings"
SLUG_PATTERN = re.compile(r"^[A-Za-z0-9_-]{24,}$")


def config():
	"""The settings as a plain dict ({} before the doctype is migrated)."""
	try:
		return frappe.db.get_singles_dict(SETTINGS) or {}
	except Exception:
		return {}


def is_owner(conf=None, user=None):
	conf = config() if conf is None else conf
	user = user or frappe.session.user
	owner = conf.get("desk_owner")
	if not (conf.get("enabled") and owner and user == owner) or user in ("Guest", "Administrator"):
		return False
	row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True) or {}
	return bool(row.get("enabled")) and row.get("user_type") == "System User"


def slug_matches(conf, slug):
	expected = conf.get("slug") or ""
	given = slug if isinstance(slug, str) else ""
	if not SLUG_PATTERN.match(expected):
		return False
	return hmac.compare_digest(expected.encode(), given.encode())


def page_gate(slug):
	"""For the page: return the settings, or raise the website 404."""
	conf = config()
	if not (is_owner(conf) and slug_matches(conf, slug)):
		raise frappe.PageDoesNotExistError
	return conf


def require_owner():
	"""For desk endpoints: return the settings, or raise a 404 (never 403, never a login prompt)."""
	conf = config()
	if not is_owner(conf):
		raise frappe.DoesNotExistError
	return conf
