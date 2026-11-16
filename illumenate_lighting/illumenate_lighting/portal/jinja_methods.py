"""Helpers exposed to website templates through the ``jinja`` hook."""


def ill_can_view_catalog() -> bool:
	"""Whether the current user may open the product catalog (Dealers and internal users).

	Named with a prefix because page contexts already use ``can_view_catalog`` as a value.
	"""
	from illumenate_lighting.illumenate_lighting.portal.access import can_view_catalog

	return can_view_catalog()


def ill_finder_enabled() -> bool:
	import frappe

	from illumenate_lighting.illumenate_lighting.portal.product_finder.content import SETTINGS

	return ill_can_view_catalog() and bool(frappe.db.get_single_value(SETTINGS, "portal_enabled"))


def ill_badge_tone(value) -> str:
	"""A badge tone from the fixed allow-list, for ``badge-{{ ... }}`` classes (plan 2.8)."""
	from illumenate_lighting.illumenate_lighting.portal.status import badge_tone

	return badge_tone(value)


def ill_sanitize_html(html) -> str:
	"""Sanitize stored rich text for ``| safe`` output.

	Frappe's template sandbox only exposes whitelisted data helpers under
	``frappe.utils``; ``sanitize_html`` is not one of them and renders as None.
	"""
	from frappe.utils.html_utils import sanitize_html

	return sanitize_html(html or "")


def ill_unread_notifications() -> int:
	"""Unread portal notifications for the nav badge (plan 8.5); 0 when switched off or for guests.

	The badge must never break page rendering, so any failure reads as "nothing unread".
	"""
	from illumenate_lighting.illumenate_lighting.portal import notification_center

	try:
		return notification_center.unread_count()
	except Exception:
		return 0


def ill_notification_center_enabled() -> bool:
	from illumenate_lighting.illumenate_lighting.portal.notification_center import enabled

	return enabled()
