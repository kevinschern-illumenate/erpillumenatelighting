"""FLOW-1: the overview's action items, one source at a time."""

import sqlite3
import types
import unittest
from datetime import date, datetime
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

TODAY = "2026-10-14"


def actor(**values):
	base = {
		"user": "dana@acme.test",
		"customer": "CUST-1",
		"is_guest": False,
		"is_dealer": True,
		"is_internal": False,
	}
	return types.SimpleNamespace(**{**base, **values})


class ActionCenter(unittest.TestCase):
	def setUp(self):
		self.can_read = MagicMock(return_value=True)
		self.conditions = MagicMock(return_value=(["raised_by = %(user)s"], {"user": "dana@acme.test"}))
		self.unconfigured = MagicMock(side_effect=lambda line: not line.get("configured_fixture"))
		self.quote_conditions = MagicMock(return_value="schedule = 'S-1'")
		self.verification_conditions = MagicMock(return_value="requested_by = 'dana@acme.test'")
		self.actor = actor()
		access = types.SimpleNamespace(get_actor=MagicMock(side_effect=lambda user=None: self.actor))
		self.extras = {
			ROOT + ".portal.access": access,
			ROOT + ".portal.offers": types.SimpleNamespace(can_read=self.can_read),
			ROOT + ".portal.support": types.SimpleNamespace(_conditions=self.conditions),
			ROOT + ".portal.quotes": types.SimpleNamespace(
				get_permission_query_conditions=self.quote_conditions
			),
			ROOT + ".portal.product_finder.verification": types.SimpleNamespace(
				get_permission_query_conditions=self.verification_conditions
			),
			ROOT
			+ ".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule": types.SimpleNamespace(
				is_unconfigured=self.unconfigured
			),
		}

	def service(self):
		context = load_service(ROOT + ".portal.action_center", self.extras)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.utils.getdate = lambda value: date.fromisoformat(str(value)[:10])
		frappe.utils.date_diff = lambda end, start: (end - start).days
		frappe.utils.nowdate = lambda: TODAY
		frappe.get_list = MagicMock(return_value=[])
		frappe.get_all = MagicMock(return_value=[])
		frappe.db.sql = MagicMock(return_value=[])
		frappe.db.escape.side_effect = lambda value: "'" + value.replace("'", "''") + "'"
		frappe.log_error = MagicMock()
		frappe.get_traceback = MagicMock(return_value="trace")
		return module, frappe

	def test_offers_soonest_expiry_first_with_a_readable_label(self):
		module, frappe = self.service()
		offers = [
			Record(name="QO-2", customer="CUST-1", quotation="Q-2", schedule="S-1", valid_until="2026-10-15"),
			Record(name="QO-1", customer="CUST-1", quotation="Q-1", schedule="S-1", valid_until="2026-10-24"),
			Record(name="QO-3", customer="CUST-1", quotation="Q-3", schedule="S-1", valid_until="2026-10-20"),
		]
		frappe.get_all.side_effect = [offers, [Record(name="S-1", schedule_name="Lobby")]]
		self.can_read.side_effect = lambda row, user: row.name != "QO-3"
		items = module.offers(self.actor, TODAY)
		filters = frappe.get_all.call_args_list[0].kwargs["filters"]
		self.assertEqual(filters, {"customer": "CUST-1", "state": "ISSUED", "valid_until": [">=", TODAY]})
		self.assertEqual(frappe.get_all.call_args_list[0].kwargs["order_by"], "valid_until asc, name asc")
		self.assertEqual([item["link"] for item in items], ["/portal/quotes/QO-2", "/portal/quotes/QO-1"])
		self.assertEqual(items[0]["due_label"], "Expires tomorrow")
		self.assertEqual(items[0]["tone"], "danger")
		self.assertEqual(items[1]["due_label"], "Expires in 10 days")
		self.assertEqual(items[1]["tone"], "warning")
		self.assertEqual(items[1]["context"], "Lobby")

	def test_staff_and_unlinked_users_get_no_offers(self):
		module, frappe = self.service()
		self.assertEqual(module.offers(actor(is_internal=True), TODAY), [])
		self.assertEqual(module.offers(actor(customer=None), TODAY), [])
		frappe.get_all.assert_not_called()

	def test_order_requests_waiting_on_the_buyer(self):
		module, _frappe = self.service()
		rows = [
			Record(name="SO-1", intake_state="INFORMATION_NEEDED", needs_action=False, po_no="PO-9"),
			Record(name="SO-2", intake_state="UNDER_REVIEW", needs_action=False),
			Record(name="SO-3", intake_state="CHANGES_PROPOSED", needs_action=True),
			Record(name="SO-4", intake_state="SUBMITTED", needs_action=True),
		]
		items = module.orders(self.actor, rows)
		self.assertEqual(
			[item["title"] for item in items],
			[
				"Answer questions on order request SO-1",
				"Review proposed changes to order request SO-3",
				"Confirm order request SO-4",
			],
		)
		self.assertEqual(items[0]["context"], "PO PO-9")
		self.assertEqual(items[2]["link"], "/portal/orders/SO-4")

	def test_drawings_to_approve_come_before_questions_and_never_twice(self):
		module, frappe = self.service()
		review = [
			Record(name="DR-1", request_type="Shop", fixture_or_product_text="LS-48", sla_deadline=None)
		]
		waiting = [
			Record(name="DR-1", request_type="Shop", fixture_or_product_text=None, sla_deadline=None),
			Record(name="DR-2", request_type="Layout", fixture_or_product_text=None, sla_deadline=None),
		]
		frappe.get_list.side_effect = [review, waiting]
		items = module.drawings(self.actor)
		self.assertEqual(
			[item["title"] for item in items],
			["Approve drawing DR-1", "Answer questions on drawing request DR-2"],
		)
		first = frappe.get_list.call_args_list[0].kwargs["filters"]
		self.assertEqual(first["technical_reviewer"], "dana@acme.test")
		self.assertEqual(first["ill_review_state"], "Awaiting approval")
		self.assertEqual(frappe.get_list.call_args_list[1].kwargs["filters"]["status"], "Waiting on Customer")
		self.assertEqual(items[1]["context"], "Layout")

	def test_staff_see_only_drawings_they_review(self):
		module, frappe = self.service()
		frappe.get_list.return_value = []
		module.drawings(actor(is_internal=True))
		self.assertEqual(frappe.get_list.call_count, 1)

	def test_tickets_and_requests_waiting_on_the_customer(self):
		module, frappe = self.service()
		frappe.db.sql.side_effect = [
			[Record(name="ISS-1", subject="Flicker")],
			[Record(name="QR-1", schedule="S-1", due_date=None)],
			[Record(name="OC-1", sales_order="SO 1", request_type="Cancellation")],
			[Record(name="PV-1", product_title="Linear 48")],
		]
		frappe.get_list.side_effect = PermissionError("Native list access is staff-only")
		items = module.waiting_on_customer(self.actor)
		sql, params = frappe.db.sql.call_args_list[0].args
		self.assertIn("raised_by = %(user)s", sql)
		self.assertIn("ill_next_action_by = 'Customer'", sql)
		self.assertIn("status not in ('Closed', 'Resolved')", sql)
		self.assertEqual(params, {"user": "dana@acme.test"})
		self.assertEqual(
			[(item["title"], item["link"]) for item in items],
			[
				("Reply to support ticket ISS-1", "/portal/support/ISS-1"),
				("Answer questions on quote request QR-1", "/portal/quote-requests/QR-1"),
				("Answer questions on cancellation request OC-1", "/portal/orders/SO%201"),
				("Answer questions on product verification PV-1", "/portal/product-verification/PV-1"),
			],
		)
		frappe.get_list.assert_not_called()
		self.quote_conditions.assert_called_once_with(self.actor.user)
		self.verification_conditions.assert_called_once_with(self.actor.user)

	def request_database(self, frappe):
		db = sqlite3.connect(":memory:")
		db.row_factory = sqlite3.Row
		self.addCleanup(db.close)
		db.executescript("""
			create table `tabIssue` (name, subject, raised_by, ill_next_action_by, status, modified);
			create table `tabilL-Quote-Request` (name, schedule, state, modified);
			create table `tabilL-Order-Change` (name, sales_order, request_type, state, modified);
			create table `tabSales Order` (name, customer);
			create table `tabilL-Product-Verification-Request`
				(name, product_title, requested_by, schedule, state, modified);
			insert into `tabilL-Quote-Request` values
				('QR-1', 'S-1', 'INFORMATION_NEEDED', '2026-10-01'),
				('QR-2', 'SHARED', 'INFORMATION_NEEDED', '2026-10-02'),
				('QR-CLOSED', 'SHARED', 'CLOSED', '2026-10-03'),
				('QR-OTHER', 'FOREIGN', 'INFORMATION_NEEDED', '2026-10-04');
			insert into `tabSales Order` values ('SO-1', 'CUST-1'), ('SO-2', 'CUST-2');
			insert into `tabilL-Order-Change` values
				('OC-1', 'SO-1', 'Change', 'INFORMATION_NEEDED', '2026-10-01'),
				('OC-OTHER', 'SO-2', 'Change', 'INFORMATION_NEEDED', '2026-10-02'),
				('OC-CLOSED', 'SO-1', 'Cancellation', 'CLOSED', '2026-10-03');
			insert into `tabilL-Product-Verification-Request` values
				('PV-OWN', 'Owned', 'dana@acme.test', null, 'INFORMATION_NEEDED', '2026-10-01'),
				('PV-SHARED', 'Shared', 'other@test', 'S-1', 'INFORMATION_NEEDED', '2026-10-02'),
				('PV-CLOSED', 'Closed', 'other@test', 'S-1', 'VERIFIED', '2026-10-03'),
				('PV-OTHER', 'Foreign', 'other@test', 'FOREIGN', 'INFORMATION_NEEDED', '2026-10-04');
		""")
		# A newer inaccessible row must not consume the visible action limit.
		db.executemany(
			"insert into `tabilL-Quote-Request` values (?, 'FOREIGN', 'INFORMATION_NEEDED', '2026-10-14')",
			[(f"FOREIGN-{index}",) for index in range(15)],
		)
		self.quote_conditions.return_value = "schedule = 'S-1' or schedule = 'SHARED'"
		self.verification_conditions.return_value = "requested_by = 'dana@acme.test' or schedule = 'S-1'"

		def query(sql, params=None, as_dict=False):
			rows = db.execute(sql.replace("%(user)s", ":user"), params or {}).fetchall()
			return [Record(dict(row)) for row in rows]

		frappe.db.sql.side_effect = query
		frappe.get_list.side_effect = PermissionError("Native list access is staff-only")

	def test_waiting_requests_keep_portal_scope_and_state_without_native_list_permission(self):
		module, frappe = self.service()
		self.request_database(frappe)
		items = module.waiting_on_customer(self.actor)
		self.assertEqual(
			[item["link"] for item in items],
			[
				"/portal/quote-requests/QR-2",
				"/portal/quote-requests/QR-1",
				"/portal/orders/SO-1",
				"/portal/product-verification/PV-SHARED",
				"/portal/product-verification/PV-OWN",
			],
		)
		frappe.get_list.assert_not_called()

	def test_order_changes_require_a_dealer_for_the_orders_current_company(self):
		module, frappe = self.service()
		self.request_database(frappe)
		for person, expected in (
			(actor(customer="CUST-2"), ["/portal/orders/SO-2"]),
			(actor(is_dealer=False), []),
			(actor(customer=None), []),
		):
			with self.subTest(person=person):
				items = module.waiting_on_customer(person)
				self.assertEqual([item["link"] for item in items if item["kind"] == "order_change"], expected)

	def test_guests_and_staff_have_no_waiting_customer_requests(self):
		module, frappe = self.service()
		for person in (actor(is_guest=True), actor(is_internal=True)):
			self.assertEqual(module.waiting_on_customer(person), [])
		frappe.db.sql.assert_not_called()
		frappe.get_list.assert_not_called()

	def test_draft_schedules_count_their_unconfigured_lines(self):
		module, frappe = self.service()
		frappe.get_list.return_value = [
			Record(name="S-1", schedule_name="Lobby", ill_project="P-1"),
			Record(name="S-2", schedule_name="Garage", ill_project="P-1"),
			Record(name="S-3", schedule_name="Roof", ill_project="P-1"),
		]
		frappe.get_all.return_value = [
			Record(parent="S-1", configured_fixture=None),
			Record(parent="S-1", configured_fixture=None),
			Record(parent="S-2", configured_fixture="CF-1"),
			Record(parent="S-3", configured_fixture=None),
		]
		items = module.schedules(self.actor)
		self.assertEqual(frappe.get_list.call_args.kwargs["filters"], {"status": "DRAFT", "is_locked": 0})
		self.assertEqual(
			[(item["title"], item["link"]) for item in items],
			[
				("Configure 2 lines in Lobby", "/portal/schedules/S-1"),
				("Configure 1 line in Roof", "/portal/schedules/S-3"),
			],
		)

	def test_staff_see_only_their_own_schedules(self):
		module, frappe = self.service()
		module.schedules(actor(is_internal=True))
		self.assertEqual(frappe.get_list.call_args.kwargs["filters"]["owner"], "dana@acme.test")
		frappe.get_all.assert_not_called()

	def test_pending_invitations_the_user_sent(self):
		module, frappe = self.service()
		frappe.get_all.return_value = [
			Record(name="INV-1", email="old@studio.test", project="P 1", expires_on="2026-10-10 09:00:00"),
			Record(name="INV-2", email="new@studio.test", project=None, expires_on="2026-10-20 09:00:00"),
		]
		items = module.invitations(self.actor, TODAY)
		self.assertEqual(
			frappe.get_all.call_args.kwargs["filters"], {"invited_by": "dana@acme.test", "state": "Pending"}
		)
		self.assertEqual(items[0]["link"], "/portal/projects/P%201/collaborators")
		self.assertEqual(items[0]["due_label"], "Expired")
		self.assertEqual(items[0]["tone"], "danger")
		self.assertEqual(items[0]["context"], "Resend it from the invitations list")
		self.assertEqual(items[1]["link"], "/portal/account")
		self.assertEqual(items[1]["due_label"], "Expires in 6 days")
		self.assertEqual(items[1]["tone"], "info")

	def test_sources_run_in_priority_order_and_a_failure_is_logged(self):
		module, frappe = self.service()
		module.offers = MagicMock(return_value=[{"kind": "offer"}])
		module.orders = MagicMock(return_value=[{"kind": "order"}])
		module.drawings = MagicMock(side_effect=RuntimeError("boom"))
		module.drawings.__name__ = "drawings"
		module.waiting_on_customer = MagicMock(return_value=[{"kind": "support"}])
		module.schedules = MagicMock(return_value=[{"kind": "schedule"}])
		module.invitations = MagicMock(return_value=[{"kind": "invitation"}])
		items = module.for_user("dana@acme.test", [])
		self.assertEqual(
			[item["kind"] for item in items], ["offer", "order", "support", "schedule", "invitation"]
		)
		self.assertEqual(frappe.log_error.call_args.kwargs["title"], "Portal action center: drawings failed")

	def test_guests_have_no_actions(self):
		module, frappe = self.service()
		self.actor = actor(is_guest=True)
		self.assertEqual(module.for_user("Guest"), [])
		frappe.get_all.assert_not_called()

	def test_greeting_follows_the_clock(self):
		module, _frappe = self.service()
		self.assertEqual(module.greeting(datetime(2026, 10, 14, 8)), "Good morning")
		self.assertEqual(module.greeting(datetime(2026, 10, 14, 13)), "Good afternoon")
		self.assertEqual(module.greeting(datetime(2026, 10, 14, 19)), "Good evening")


if __name__ == "__main__":
	unittest.main()
