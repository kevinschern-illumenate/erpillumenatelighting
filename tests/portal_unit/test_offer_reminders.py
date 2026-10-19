"""DESK-10: buyers are reminded before an issued offer expires; staff see it in a queue."""

import types
import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


class OfferReminders(unittest.TestCase):
	def service(self):
		self.notify = MagicMock()
		access = types.SimpleNamespace(can_read_schedule=MagicMock(return_value=True), get_actor=MagicMock())
		staff = types.SimpleNamespace(allowed=MagicMock(return_value=False), require=MagicMock())
		notifications = types.SimpleNamespace(
			notify_user=self.notify, _portal_link=lambda path, label: f'<a href="{path}">{label}</a>'
		)
		context = load_service(
			ROOT + ".portal.offers",
			{
				ROOT + ".portal.access": access,
				ROOT + ".portal.staff": staff,
				ROOT + ".portal.notifications": notifications,
			},
		)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		module.nowdate = lambda: "2026-10-14"
		module.getdate = lambda value: date.fromisoformat(str(value)[:10])
		frappe.utils.add_days = lambda value, days: value + timedelta(days=days)
		frappe.utils.escape_html = lambda value: str(value).replace("<", "&lt;")
		frappe.utils.format_date = str
		return module, frappe

	def test_three_day_and_one_day_reminders_go_to_buyers_who_can_open_the_offer(self):
		module, frappe = self.service()
		offers = {
			date(2026, 10, 17): [
				Record(name="QO-3", schedule="S-1", quote_request="QR-1", valid_until="2026-10-17")
			],
			date(2026, 10, 15): [
				Record(name="QO-1", schedule="S-2", quote_request=None, valid_until="2026-10-15")
			],
		}
		frappe.get_all.side_effect = lambda doctype, filters, fields: offers[filters["valid_until"]]
		frappe.db.get_value.side_effect = lambda doctype, name, field: {
			("ilL-Quote-Request", "requested_by"): "buyer@acme.test",
			("ilL-Project-Fixture-Schedule", "owner"): "owner@acme.test",
		}[(doctype, field)]
		module.can_read = lambda offer, user: user != "owner@acme.test" or offer.name == "QO-1"
		module.remind_expiring()
		sent = [(call.args[0], call.args[1], call.kwargs["event_key"]) for call in self.notify.call_args_list]
		self.assertEqual(
			sent,
			[
				("buyer@acme.test", "notify_quotes", "QO-3:expiring:2026-10-17:3"),
				("owner@acme.test", "notify_quotes", "QO-1:expiring:2026-10-15:1"),
			],
		)
		self.assertEqual(self.notify.call_args_list[1].args[2], "Quote QO-1 expires tomorrow")
		self.assertIn("/portal/quotes/QO-3", self.notify.call_args_list[0].args[3])
		self.assertEqual(frappe.get_all.call_args_list[0].kwargs["filters"]["state"], "ISSUED")

	def test_staff_queue_lists_offers_valid_for_three_more_days_at_most(self):
		module, _frappe = self.service()
		self.assertEqual(
			module.expiring_queue_filters(),
			{"valid_until": ["between", [date(2026, 10, 14), date(2026, 10, 17)]]},
		)


if __name__ == "__main__":
	unittest.main()
