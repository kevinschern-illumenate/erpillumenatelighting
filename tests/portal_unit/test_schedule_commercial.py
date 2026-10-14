"""FLOW-2: the schedule page's stepper, commercial thread and next step."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


class Row(Record):
	def __setattr__(self, key, value):
		self[key] = value


class ScheduleCommercial(unittest.TestCase):
	def setUp(self):
		self.can_read = MagicMock(return_value=True)
		self.order = MagicMock(return_value=None)
		quotes = types.SimpleNamespace(
			REQUEST_LABELS={
				"REQUESTED": ("Received", "info"),
				"INFORMATION_NEEDED": ("Needs your reply", "warning"),
			}
		)
		offers = types.SimpleNamespace(
			can_read=self.can_read,
			offer_status=lambda state, valid_until, today: (
				("Expired", "danger")
				if state == "ISSUED" and valid_until and valid_until < today
				else ({"ISSUED": ("Awaiting your response", "warning")}.get(state, (state, "secondary")))
			),
		)
		status = types.SimpleNamespace(
			derive_order_portal_status=lambda docstatus, *args: (
				"order_request" if docstatus == 0 else "approved"
			),
			order_status_label=lambda key: key.replace("_", " ").title(),
			order_status_class=lambda key: "warning",
		)
		self.extras = {
			ROOT + ".portal.quotes": quotes,
			ROOT + ".portal.offers": offers,
			ROOT + ".portal.orders": types.SimpleNamespace(load_accessible_sales_order=self.order),
			ROOT + ".portal.status": status,
			ROOT
			+ ".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule": types.SimpleNamespace(
				is_unconfigured=lambda line: not line.get("configured_fixture")
			),
		}

	def service(self):
		context = load_service(ROOT + ".portal.schedule_commercial", self.extras)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe._dict = Row
		frappe.utils.nowdate = lambda: "2026-10-14"
		frappe.utils.strip_html = lambda value: value.replace("<p>", "").replace("</p>", "")
		frappe.get_all = MagicMock(return_value=[])
		return module, frappe

	def thread(self, requests=(), offers=(), order=None):
		return Row(requests=list(requests), offers=list(offers), order=order)

	def test_stepper_marks_done_current_and_upcoming(self):
		module, _frappe = self.service()
		steps = module.progress("QUOTED", self.thread())
		self.assertEqual(
			[(step["key"], step["state"]) for step in steps],
			[
				("build", "done"),
				("ready", "done"),
				("quote_requested", "done"),
				("quoted", "current"),
				("order_requested", "upcoming"),
				("ordered", "upcoming"),
			],
		)

	def test_an_open_request_moves_a_ready_schedule_to_quote_requested(self):
		module, _frappe = self.service()
		open_request = Row(is_open=True)
		self.assertEqual(module.current_step("READY", self.thread([open_request])), "quote_requested")
		self.assertEqual(module.current_step("READY", self.thread([Row(is_open=False)])), "ready")
		self.assertEqual(module.current_step("DRAFT", self.thread([open_request])), "build")

	def test_an_order_issue_is_flagged_on_its_step(self):
		module, _frappe = self.service()
		steps = {step["key"]: step for step in module.progress("ISSUE", self.thread())}
		self.assertEqual(steps["order_requested"]["state"], "current")
		self.assertTrue(steps["order_requested"]["problem"])

	def next(self, status, commercial=None, **options):
		module, _frappe = self.service()
		schedule = Row(status=status, is_locked=options.pop("locked", 0))
		defaults = {"can_edit": True, "can_create_order": False, "unconfigured": []}
		return module.next_step(schedule, commercial or self.thread(), **{**defaults, **options})

	def test_draft_offers_mark_ready_with_a_reason_while_lines_are_open(self):
		step = self.next("DRAFT", unconfigured=["A1", "Row 2"])
		self.assertEqual(step["primary"]["action"], "ready")
		self.assertEqual(step["primary"]["disabled_reason"], "Configure these lines first: A1, Row 2")
		self.assertNotIn("disabled_reason", self.next("DRAFT")["primary"])
		self.assertIsNone(self.next("DRAFT", can_edit=False)["primary"])
		self.assertIsNone(self.next("DRAFT", locked=1)["primary"])

	def test_ready_requests_a_quote_with_ordering_directly_second(self):
		step = self.next("READY", can_create_order=True)
		self.assertEqual(step["primary"], {"label": "Request quote", "action": "quote"})
		self.assertEqual(step["secondary"], {"label": "Order directly", "action": "order"})
		self.assertIsNone(self.next("READY")["secondary"])

	def test_ready_with_an_open_request_links_to_it(self):
		request = Row(is_open=True, link="/portal/quote-requests/QR-1")
		step = self.next("READY", self.thread([request]))
		self.assertEqual(
			step["primary"], {"label": "View quote request", "href": "/portal/quote-requests/QR-1"}
		)

	def test_quoted_reviews_the_open_offer_and_orders_link_to_the_order(self):
		offer = Row(is_open=True, link="/portal/quotes/QO-1")
		self.assertEqual(
			self.next("QUOTED", self.thread(offers=[offer]))["primary"]["href"], "/portal/quotes/QO-1"
		)
		self.assertIsNone(self.next("QUOTED", self.thread(offers=[Row(is_open=False)]))["primary"])
		order = Row(link="/portal/orders/SO-1")
		for status in ("ORDER_REQUESTED", "ORDERED"):
			step = self.next(status, self.thread(order=order))
			self.assertEqual(step["primary"], {"label": "View order", "href": "/portal/orders/SO-1"})

	def test_requests_carry_owner_and_last_customer_message(self):
		module, frappe = self.service()
		frappe.get_all.side_effect = [
			[Row(name="QR-1", state="INFORMATION_NEEDED", assigned_to="sam@illumenate.test")],
			[Row(body="<p>" + "x" * 150 + "</p>")],
		]
		frappe.db.get_value.return_value = "Sam Staff"
		rows = module.requests_for("S-1")
		self.assertEqual(
			frappe.get_all.call_args_list[0].kwargs["filters"], {"schedule": "S-1", "state": ["!=", "DRAFT"]}
		)
		message_filters = frappe.get_all.call_args_list[1].kwargs["filters"]
		self.assertEqual(message_filters["visibility"], "Customer")
		self.assertEqual(rows[0].status_label, "Needs your reply")
		self.assertEqual(rows[0].assigned_name, "Sam Staff")
		self.assertEqual(rows[0].last_message, "x" * 140 + "…")
		self.assertEqual(rows[0].link, "/portal/quote-requests/QR-1")
		self.assertTrue(rows[0].is_open)

	def test_offers_are_listed_only_when_the_viewer_may_open_them(self):
		module, frappe = self.service()
		frappe.get_all.return_value = [
			Row(name="QO-2", state="ISSUED", valid_until="2026-10-01"),
			Row(name="QO-1", state="ISSUED", valid_until="2026-10-30"),
			Row(name="QO-0", state="ISSUED", valid_until=None),
		]
		self.can_read.side_effect = lambda row, user: row.name != "QO-0"
		rows = module.offers_for("S-1", "dana@acme.test")
		self.assertEqual([row.name for row in rows], ["QO-2", "QO-1"])
		self.assertEqual((rows[0].status_label, rows[0].is_open), ("Expired", False))
		self.assertEqual((rows[1].status_label, rows[1].is_open), ("Awaiting your response", True))

	def test_order_shows_only_when_accessible(self):
		module, _frappe = self.service()
		self.assertIsNone(module.order_for(Row(sales_order="SO-1"), "dana@acme.test"))
		self.order.return_value = Row(name="SO 1", docstatus=0, status="Draft")
		order = module.order_for(Row(sales_order="SO 1"), "dana@acme.test")
		self.assertEqual(
			(order.link, order.status_label, order.is_request),
			("/portal/orders/SO%201", "Order Request", True),
		)

	def test_unconfigured_lines_name_and_anchor_each_line(self):
		module, _frappe = self.service()
		lines = [
			Row(line_id="A1", line_key="k1", configured_fixture=None, idx=1),
			Row(line_id=None, line_key=None, name="row-2", configured_fixture=None, idx=2),
			Row(line_id="A3", line_key="k3", configured_fixture="CF", idx=3),
		]
		self.assertEqual(module.unconfigured_lines(lines), [("A1", "k1"), ("Row 2", "row-2")])


if __name__ == "__main__":
	unittest.main()
