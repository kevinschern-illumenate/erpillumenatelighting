"""Kevin's Desk endpoints. Every one starts with ``access.require_owner()``.

They are ``allow_guest`` only so that a guest gets the same 404 as any other non-owner, from our own
check, instead of Frappe's "not whitelisted for guests" 403 that would show the method exists. Nothing
runs before the owner check (tests/portal_unit/test_kevins_desk_pipeline.py enforces it). Like every guest
endpoint in the app, each is rate-limited (tests/portal_unit/test_guest_endpoints.py).

Reads are cached per user for TTL seconds; ``refresh=1`` rebuilds. The cache keeps the page under
3 seconds; the Refresh button is the way to see a change made a moment ago.
"""

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, now_datetime

from illumenate_lighting.kevins_desk import access
from illumenate_lighting.kevins_desk import pipeline as pipe

TTL = 300  # seconds


def cached(key, build, refresh=False):
	cache_key = f"kevins_desk:{frappe.session.user}:{key}"
	if not refresh:
		hit = frappe.cache().get_value(cache_key)
		if hit:
			return dict(hit, cached=True)
	data = build()
	data["built_at"] = now_datetime().isoformat(timespec="seconds")
	frappe.cache().set_value(cache_key, data, expires_in_sec=TTL)
	return dict(data, cached=False)


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=120, seconds=60)
def pipeline(refresh=0):
	"""Pipeline widgets (through the Command Center gateway) and the owner's ToDos."""
	conf = access.require_owner()
	return cached("pipeline", lambda: pipe.build(conf["desk_owner"]), cint(refresh))


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=120, seconds=60)
def signals(refresh=0):
	"""The Command Center's 'Decisions this week' counts."""
	access.require_owner()
	return cached("signals", pipe.signals, cint(refresh))
