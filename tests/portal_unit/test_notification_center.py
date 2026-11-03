"""Plan 8.5: the notification center reads the outbox ledger, re-checks access and keeps a per-user seen marker."""

import types
import unittest
from datetime import datetime
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".portal.notification_center"
PAGE = "illumenate_lighting.templates.pages.ill_notifications"


def services(access=lambda event, user: True, flag=True):
	return {
		ROOT + ".portal.outbox": types.SimpleNamespace(
			DELIVERY="ilL-Portal-Delivery", EVENT="ilL-Portal-Event", reference_access=MagicMock(side_effect=access)
		),
		ROOT + ".portal.notifications": types.SimpleNamespace(
			PREFERENCE_DEFAULTS={"notify_orders": True, "notify_quotes": True}
		),
		ROOT + ".portal.site_flags": types.SimpleNamespace(conf_flag=MagicMock(return_value=flag)),
	}


def ledger(frappe, deliveries, events):
	def get_all(doctype, **kwargs):
		return deliveries if doctype == "ilL-Portal-Delivery" else events

	frappe.get_all.side_effect = get_all
	frappe.defaults = types.SimpleNamespace(get_user_default=MagicMock(return_value=None), set_user_default=MagicMock())


DELIVERIES = [
	Record(name="D3", event="E3", creation=datetime(2026, 11, 3)),
	Record(name="D2", event="E2", creation=datetime(2026, 11, 2)),
	Record(name="D2b", event="E2", creation=datetime(2026, 11, 2)),
	Record(name="D1", event="E1", creation=datetime(2026, 11, 1)),
]
EVENTS = [
	Record(name="E3", subject="Quote ready", reference_type="ilL-Quote-Offer", reference_name="OFFER/1", preference="notify_quotes"),
	Record(name="E2", subject="Order shipped", reference_type="Sales Order", reference_name="SO-1", preference="notify_orders"),
	Record(name="E1", subject="Lost", reference_type="Sales Order", reference_name="SO-9", preference="notify_orders"),
]


class NotificationCenter(unittest.TestCase):
	def test_recent_dedupes_rechecks_access_and_links_to_the_record(self):
		def access(event, user):
			return event.reference_name != "SO-9"

		with load_service(MODULE, services(access)) as (module, frappe):
			ledger(frappe, DELIVERIES, EVENTS)
			frappe.defaults.get_user_default.return_value = "2026-11-02 12:00:00"
			entries = module.recent()
		self.assertEqual([e["subject"] for e in entries], ["Quote ready", "Order shipped"])
		self.assertEqual(entries[0]["link"], "/portal/quotes/OFFER%2F1")
		self.assertEqual([e["unread"] for e in entries], [True, False])

	def test_ledger_query_is_scoped_to_the_user_and_skips_unreachable_states(self):
		with load_service(MODULE, services()) as (module, frappe):
			ledger(frappe, DELIVERIES, EVENTS)
			module.recent()
			kwargs = frappe.get_all.call_args_list[0].kwargs
			self.assertEqual(kwargs["filters"]["recipient"], "buyer@example.com")
			self.assertNotIn("SKIPPED", kwargs["filters"]["state"][1])
			events = frappe.get_all.call_args_list[1].kwargs["filters"]
			self.assertEqual(sorted(events["preference"][1]), ["notify_orders", "notify_quotes"])

	def test_access_errors_hide_the_entry_instead_of_breaking_the_page(self):
		def access(event, user):
			raise LookupError("deleted")

		with load_service(MODULE, services(access)) as (module, frappe):
			ledger(frappe, DELIVERIES, EVENTS)
			self.assertEqual(module.recent(), [])

	def test_unread_count_uses_the_seen_marker_caps_and_caches(self):
		many = [Record(name=f"D{i}", event=f"E{i}", creation=datetime(2026, 11, 1)) for i in range(15)]
		events = [Record(name=f"E{i}", subject="x", reference_type="Issue", reference_name=f"I{i}", preference="notify_orders") for i in range(15)]
		with load_service(MODULE, services()) as (module, frappe):
			ledger(frappe, many, events)
			frappe.defaults.get_user_default.return_value = "2026-10-31 00:00:00"
			self.assertEqual(module.unread_count(), 10)
			self.assertEqual(module.badge_label(10), "9+")
			since = frappe.get_all.call_args_list[0].kwargs["filters"]["creation"]
			self.assertEqual(since, [">", datetime(2026, 10, 31)])
			frappe.cache().set_value.assert_called_once_with("ill_portal_unread::buyer@example.com", 10, expires_in_sec=60)
			frappe.cache().get_value.return_value = 3
			frappe.get_all.reset_mock()
			self.assertEqual(module.unread_count(), 3)
			frappe.get_all.assert_not_called()

	def test_kill_switch_and_guests_read_zero_without_queries(self):
		with load_service(MODULE, services(flag=False)) as (module, frappe):
			ledger(frappe, DELIVERIES, EVENTS)
			self.assertEqual(module.unread_count(), 0)
			frappe.session.user = "Guest"
			self.assertEqual(module.recent(), [])
			frappe.get_all.assert_not_called()

	def test_mark_seen_sets_the_user_default_and_clears_the_badge_cache(self):
		with load_service(MODULE, services()) as (module, frappe):
			ledger(frappe, [], [])
			module.mark_seen()
			frappe.defaults.set_user_default.assert_called_once_with(
				"ill_portal_notifications_seen_at", "2026-09-25 12:00:00", "buyer@example.com"
			)
			frappe.cache().delete_value.assert_called_once_with("ill_portal_unread::buyer@example.com")

	def test_links_for_child_records_resolve_to_their_portal_page(self):
		with load_service(MODULE, services()) as (module, frappe):
			frappe.db.get_value.side_effect = lambda doctype, name, field, **kw: (
				"SO 7" if field == "sales_order" else Record(reference_type="Issue", reference_name="ISS-1")
			)
			self.assertEqual(module.link("ilL-Order-Change", "OC1"), "/portal/orders/SO%207")
			self.assertEqual(module.link("ilL-Portal-Message", "M1"), "/portal/support/ISS-1")
			self.assertEqual(module.link("Delivery Note", "DN1"), "/portal/orders")
			self.assertEqual(module.link("Unknown", "X"), "/portal")


class NotificationsPage(unittest.TestCase):
	def center(self, enabled=True):
		return types.SimpleNamespace(
			enabled=MagicMock(return_value=enabled),
			recent=MagicMock(return_value=[{"subject": "s", "link": "/portal", "when": "w", "unread": True}]),
			mark_seen=MagicMock(),
		)

	def load(self, center):
		portal = types.SimpleNamespace(notification_center=center)
		guard = types.SimpleNamespace(require_login=MagicMock())
		return load_service(PAGE, {ROOT + ".portal": portal, ROOT + ".portal.notification_center": center, ROOT + ".portal.web_guard": guard})

	def test_page_lists_then_marks_seen(self):
		center = self.center()
		with self.load(center) as (page, frappe):
			frappe.utils.pretty_date = lambda value: "just now"
			context = page.get_context(Record())
		self.assertEqual(context.notifications[0]["when_label"], "just now")
		self.assertTrue(context.notifications[0]["unread"])
		center.mark_seen.assert_called_once_with()

	def test_switched_off_page_redirects_home(self):
		center = self.center(enabled=False)
		with self.load(center) as (page, frappe):
			frappe.Redirect = type("Redirect", (Exception,), {})
			frappe.local.flags = Record()
			with self.assertRaises(frappe.Redirect):
				page.get_context(Record())
			self.assertEqual(frappe.local.flags.redirect_location, "/portal")
		center.mark_seen.assert_not_called()


if __name__ == "__main__":
	unittest.main()
