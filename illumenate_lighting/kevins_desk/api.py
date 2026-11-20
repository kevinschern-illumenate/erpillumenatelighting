"""Kevin's Desk endpoints. Every one starts with ``access.require_owner()``.

They are ``allow_guest`` only so that a guest gets the same 404 as any other non-owner, from our own
check, instead of Frappe's "not whitelisted for guests" 403 that would show the method exists. Nothing
runs before the owner check (tests/portal_unit/test_kevins_desk_pipeline.py enforces it). Like every guest
endpoint in the app, each is rate-limited (tests/portal_unit/test_guest_endpoints.py).

Reads are cached per user (pipeline 5 min, mail 10 min, decisions 5 min); ``refresh=1`` rebuilds.
tasks.warm rebuilds them every 10 minutes on weekdays, so a page load normally hits the cache.
"""

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, now_datetime

from illumenate_lighting.kevins_desk import access, mail, mailboxes, ranking, schedule, team
from illumenate_lighting.kevins_desk import pipeline as pipe

TTL = {"pipeline": 300, "mail": 600, "signals": 300}


def cached(key, build, refresh=False):
	cache_key = f"kevins_desk:{frappe.session.user}:{key}"
	if not refresh:
		hit = frappe.cache().get_value(cache_key)
		if hit:
			return dict(hit, cached=True)
	data = build()
	data["built_at"] = now_datetime().isoformat(timespec="seconds")
	frappe.cache().set_value(cache_key, data, expires_in_sec=TTL[key])
	return dict(data, cached=False)


def build_today(owner, refresh=False):
	members = team.resolve()
	pipeline_data = cached("pipeline", lambda: pipe.build(owner), refresh)
	mail_data = cached("mail", lambda: mail.build(owner, members), refresh)
	return {
		"pipeline": pipeline_data,
		"mailboxes": mail_data.get("mailboxes") or [],
		"list": ranking.merge(pipeline_data, mail_data, members, schedule.HATS),
		"built_at": min(pipeline_data["built_at"], mail_data["built_at"]),
		"cached": pipeline_data["cached"] and mail_data["cached"],
	}


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=120, seconds=60)
def today(refresh=0):
	"""Pipeline widgets, ToDos, mailbox states and the merged list ranked by the priority stack."""
	conf = access.require_owner()
	return build_today(conf["desk_owner"], cint(refresh))


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=120, seconds=60)
def signals(refresh=0):
	"""The Command Center's 'Decisions this week' counts."""
	access.require_owner()
	return cached("signals", pipe.signals, cint(refresh))


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def connect_mailbox(mailbox=None):
	"""Start Google's consent flow for one of the desk's mailboxes; the page then goes to the returned URL."""
	conf = access.require_owner()
	url = mailboxes.connect(mailbox, conf["desk_owner"], f"/kd/{conf['slug']}?mailbox=connected")
	frappe.cache().delete_value(f"kevins_desk:{frappe.session.user}:mail")
	return {"authorize_url": url}
