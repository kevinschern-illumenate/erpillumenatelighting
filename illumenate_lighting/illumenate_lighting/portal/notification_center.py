"""Portal notification center (hardening plan 8.5): an unread badge and list over the outbox ledger.

``portal.outbox`` already records one ilL-Portal-Delivery per recipient for every dealer-facing
event. This module only reads that ledger: it never sends mail and never changes a delivery.
"Seen" is a per-user default, so the feature needs no schema change. Every entry is re-checked
with ``outbox.reference_access`` so a dealer who lost access to a record no longer sees it.
"""

from urllib.parse import quote

import frappe

from illumenate_lighting.illumenate_lighting.portal.notifications import PREFERENCE_DEFAULTS
from illumenate_lighting.illumenate_lighting.portal.outbox import DELIVERY, EVENT, reference_access
from illumenate_lighting.illumenate_lighting.portal.site_flags import conf_flag

FLAG = "ill_portal_notification_center"
SEEN_KEY = "ill_portal_notifications_seen_at"
BADGE_CAP = 9
LIST_LIMIT = 30
CACHE_SECONDS = 60
# SKIPPED means the account or its access was gone when the event was recorded.
VISIBLE_STATES = ("PENDING", "SUPPRESSED", "QUEUED", "FAILED", "DELIVERED")

_PATHS = {
	"Sales Order": "/portal/orders/{}",
	"ilL-Quote-Offer": "/portal/quotes/{}",
	"ilL-Quote-Request": "/portal/quote-requests/{}",
	"Issue": "/portal/support/{}",
	"ilL-Document-Request": "/portal/drawings/{}",
	"ilL-Project-Fixture-Schedule": "/portal/schedules/{}",
}


def enabled():
	"""Kill switch (D5): on unless a site sets ``ill_portal_notification_center`` false."""
	return conf_flag(FLAG, default=True)


def _user(user=None):
	user = user or frappe.session.user
	return None if not user or user in ("Guest", "Administrator") else user


def _cache_key(user):
	return f"ill_portal_unread::{user}"


def link(reference_type, reference_name, depth=0):
	"""The portal page for an event's record; the section list when there is no detail page."""
	if reference_type in _PATHS and reference_name:
		return _PATHS[reference_type].format(quote(str(reference_name), safe=""))
	if reference_type in ("ilL-Order-Change", "ilL-Order-Intake"):
		order = frappe.db.get_value(reference_type, reference_name, "sales_order")
		return link("Sales Order", order) if order else "/portal/orders"
	if reference_type == "Delivery Note":
		return "/portal/orders"
	if reference_type == "ilL-Portal-Message" and depth == 0:
		parent = frappe.db.get_value(reference_type, reference_name, ["reference_type", "reference_name"], as_dict=True)
		if parent:
			return link(parent.reference_type, parent.reference_name, depth + 1)
	return "/portal"


def seen_at(user):
	value = frappe.defaults.get_user_default(SEEN_KEY, user)
	if not value:
		return None
	try:
		return frappe.utils.get_datetime(value)
	except (TypeError, ValueError):
		return None


def _readable(event, user):
	try:
		return bool(reference_access(event, user))
	except Exception:
		# A deleted or half-migrated record must not break every portal page's nav.
		return False


def _entries(user, limit, since=None):
	filters = {"recipient": user, "state": ["in", list(VISIBLE_STATES)]}
	if since:
		filters["creation"] = [">", since]
	rows = frappe.get_all(
		DELIVERY,
		filters=filters,
		fields=["name", "event", "creation"],
		order_by="creation desc",
		limit_page_length=limit,
	)
	if not rows:
		return []
	events = {
		event.name: event
		for event in frappe.get_all(
			EVENT,
			filters={"name": ["in", list({row.event for row in rows})], "preference": ["in", list(PREFERENCE_DEFAULTS)]},
			fields=["name", "subject", "reference_type", "reference_name", "preference"],
		)
	}
	entries, shown = [], set()
	for row in rows:
		event = events.get(row.event)
		if not event or event.name in shown or not _readable(event, user):
			continue
		shown.add(event.name)
		entries.append((row, event))
	return entries


def recent(user=None, limit=LIST_LIMIT):
	"""Newest accessible notifications for ``user``, each flagged unread against the seen marker."""
	user = _user(user)
	if not user:
		return []
	seen = seen_at(user)
	return [
		{
			"subject": event.subject or "",
			"link": link(event.reference_type, event.reference_name),
			"when": row.creation,
			"unread": seen is None or frappe.utils.get_datetime(row.creation) > seen,
		}
		for row, event in _entries(user, limit)
	]


def unread_count(user=None):
	"""Unread notifications, capped at ``BADGE_CAP + 1`` (shown as "9+"); 0 when off or a guest."""
	user = _user(user)
	if not user or not enabled():
		return 0
	cached = frappe.cache().get_value(_cache_key(user))
	if cached is not None:
		return int(cached)
	# Read a few extra rows so lost-access or duplicate entries do not hide a real "9+".
	count = min(len(_entries(user, (BADGE_CAP + 1) * 3, since=seen_at(user))), BADGE_CAP + 1)
	frappe.cache().set_value(_cache_key(user), count, expires_in_sec=CACHE_SECONDS)
	return count


def badge_label(count):
	return f"{BADGE_CAP}+" if count > BADGE_CAP else str(count)


def mark_seen(user=None):
	"""Opening the notification list marks everything up to now as read."""
	user = _user(user)
	if not user:
		return
	frappe.defaults.set_user_default(SEEN_KEY, str(frappe.utils.now_datetime()), user)
	frappe.cache().delete_value(_cache_key(user))
