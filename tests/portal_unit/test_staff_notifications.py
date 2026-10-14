"""Dealer submissions reach staff and get an owner (DESK-1, DESK-2, DESK-3)."""

import ast
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

NOW = datetime(2026, 10, 14, 9)
SALES = ["amy@illumenate.test", "bob@illumenate.test", "cy@illumenate.test"]


class Harness:
	"""staff_notifications over a small in-memory Desk."""

	def __init__(self, routes=(), inbox=True, open_quotes=(), settings=True):
		self.routes = [Record(row) for row in routes]
		self.inbox = inbox
		self.open_quotes = list(open_quotes)
		self.has_settings = settings
		self.logs = []
		self.existing_logs = set()

	def __enter__(self):
		self.outbox = types.SimpleNamespace(record_staff_inbox=MagicMock(return_value=True))
		queues = types.SimpleNamespace(
			QUEUES={"quotes": (None, None, None, {"state": ["in", ["REQUESTED"]]})}
		)
		deps = {
			ROOT + ".portal.staff": types.SimpleNamespace(
				CAPABILITIES={
					"sales": {"ilL Sales Review"},
					"support": {"ilL Support"},
					"accounts": {"ilL Support"},
				}
			),
			ROOT + ".portal.outbox": self.outbox,
			ROOT + ".portal.queues": queues,
			ROOT + ".portal.status": types.SimpleNamespace(SALES_EMAIL="sales@illumenate.lighting"),
		}
		self._context = load_service(ROOT + ".portal.staff_notifications", deps)
		module, frappe = self._context.__enter__()
		frappe.session = Record(user="dealer@acme.test")
		frappe.utils.now_datetime = lambda: NOW
		frappe.utils.add_to_date = lambda value, hours=0: value + timedelta(hours=hours)
		frappe.utils.getdate = lambda value: value.date()
		frappe.utils.get_url = lambda path="": "https://erp.test" + path
		frappe.utils.escape_html = lambda value: str(value).replace("<", "&lt;").replace(">", "&gt;")
		frappe.get_traceback = lambda: "Traceback"
		frappe.log_error = MagicMock()
		config = Record(routes=self.routes, email_staff_inbox=int(self.inbox), staff_inbox_email=None)
		if self.has_settings:
			frappe.get_cached_doc = MagicMock(return_value=config)
		else:
			frappe.get_cached_doc = MagicMock(side_effect=LookupError("not migrated"))

		def get_all(doctype, filters=None, pluck=None, **kw):
			if doctype == "Has Role":
				return [*SALES, "Administrator"]
			if doctype == "User":
				return [user for user in filters["name"][1] if user in SALES]
			if doctype == "ilL-Quote-Request":
				self.quote_filters = filters
				return self.open_quotes
			return []

		frappe.get_all = MagicMock(side_effect=get_all)
		frappe.db.exists.side_effect = lambda doctype, filters=None: (
			doctype == "Notification Log" and filters["for_user"] in self.existing_logs
		)
		names = {
			("Customer", "customer_name"): "Acme <Lighting>",
			("ilL-Project", "project_name"): "Lobby Refit",
			("ilL-Project-Fixture-Schedule", "schedule_name"): "Level 1",
		}
		frappe.db.get_value.side_effect = lambda doctype, name, field=None, *a, **kw: names.get(
			(doctype, field)
		)
		frappe.get_doc.side_effect = lambda values: Record(
			values, insert=lambda **kw: self.logs.append(values)
		)
		self.module, self.frappe = module, frappe
		return self

	def __exit__(self, *exc):
		return self._context.__exit__(*exc)


def quote_request(**values):
	doc = Record(
		doctype="ilL-Quote-Request",
		name="QR-0042",
		customer="CUST-1",
		project="P-1",
		schedule="S-1",
		requested_by="dealer@acme.test",
		notes="Need by spring",
		**values,
	)
	doc.update = lambda changes: dict.update(doc, changes)
	return doc


class Submissions(unittest.TestCase):
	def test_default_assignee_gets_the_request_its_due_date_and_the_only_bell(self):
		routes = [{"queue": "quotes", "default_assignee": "bob@illumenate.test", "sla_hours": 48}]
		with Harness(routes) as h:
			doc = quote_request()
			h.module.submitted(doc)
			values = h.frappe.db.set_value.call_args.args[2]
			self.assertEqual(
				values, {"assigned_to": "bob@illumenate.test", "due_date": (NOW + timedelta(hours=48)).date()}
			)
			self.assertEqual([log["for_user"] for log in h.logs], ["bob@illumenate.test"])
			log = h.logs[0]
			self.assertEqual(log["subject"], "New quote request QR-0042 from Acme <Lighting>")
			self.assertEqual(
				(log["document_type"], log["document_name"], log["type"]),
				("ilL-Quote-Request", "QR-0042", "Alert"),
			)
			for text in (
				"Acme &lt;Lighting&gt;",
				"Lobby Refit",
				"Level 1",
				"Need by spring",
				"https://erp.test/app/ill-quote-request/QR-0042",
			):
				self.assertIn(text, log["email_content"])
			inbox = h.outbox.record_staff_inbox.call_args.args
			self.assertEqual(inbox[0], "sales@illumenate.lighting")
			self.assertEqual(inbox[3:], ("ilL-Quote-Request", "QR-0042", "submitted"))

	def test_without_a_default_the_least_loaded_role_member_is_assigned(self):
		open_quotes = ["amy@illumenate.test", "amy@illumenate.test", "bob@illumenate.test"]
		with Harness(open_quotes=open_quotes) as h:
			doc = quote_request()
			h.module.submitted(doc)
			self.assertEqual(doc.assigned_to, "cy@illumenate.test")
			self.assertEqual(h.quote_filters["state"], ["in", ["REQUESTED"]], "only open items count")
			self.assertNotIn("due_date", h.frappe.db.set_value.call_args.args[2], "no SLA configured")

	def test_ties_break_by_name_so_the_choice_is_repeatable(self):
		with Harness(open_quotes=["cy@illumenate.test"]) as h:
			self.assertEqual(h.module.pick_assignee("quotes"), "amy@illumenate.test")

	def test_disabled_default_assignee_falls_back_to_the_role(self):
		routes = [{"queue": "quotes", "default_assignee": "gone@illumenate.test"}]
		with Harness(routes) as h:
			self.assertEqual(h.module.pick_assignee("quotes"), "amy@illumenate.test")

	def test_existing_owner_is_kept(self):
		with Harness() as h:
			doc = quote_request(assigned_to="cy@illumenate.test")
			h.module.submitted(doc)
			self.assertEqual(doc.assigned_to, "cy@illumenate.test")
			self.assertEqual([log["for_user"] for log in h.logs], ["cy@illumenate.test"])

	def test_resubmission_rings_nobody_twice(self):
		with Harness() as h:
			h.existing_logs = {"cy@illumenate.test"}
			h.module.submitted(quote_request(assigned_to="cy@illumenate.test"))
			self.assertEqual(h.logs, [])

	def test_inbox_email_can_be_switched_off(self):
		with Harness(inbox=False) as h:
			h.module.submitted(quote_request())
			h.outbox.record_staff_inbox.assert_not_called()
			self.assertEqual(len(h.logs), 1)

	def test_before_migration_defaults_still_notify(self):
		with Harness(settings=False) as h:
			h.module.submitted(quote_request())
			self.assertEqual(len(h.logs), 1)
			h.outbox.record_staff_inbox.assert_called_once()

	def test_routing_failure_never_undoes_the_submission(self):
		with Harness() as h:
			h.frappe.get_doc.side_effect = RuntimeError("Notification Log locked")
			self.assertIsNone(h.module.submitted(quote_request()))
			h.frappe.db.rollback.assert_called_once_with(save_point="portal_staff_routing")
			self.assertTrue(h.frappe.log_error.call_args.kwargs["defer_insert"])

	def test_order_change_subject_names_the_request_type(self):
		with Harness() as h:
			doc = Record(
				doctype="ilL-Order-Change",
				name="OC-7",
				customer="CUST-1",
				request_type="Cancellation",
				sales_order="SO-9",
				assigned_to="amy@illumenate.test",
			)
			doc.update = lambda changes: dict.update(doc, changes)
			h.module.submitted(doc)
			self.assertEqual(h.logs[0]["subject"], "New cancellation request OC-7 from Acme <Lighting>")


class Replies(unittest.TestCase):
	def message(self):
		return Record(name="MSG-1", body="Any update?")

	def test_unowned_reply_tells_the_team_and_the_inbox(self):
		with Harness() as h:
			h.module.reply(quote_request(), self.message())
			self.assertEqual(sorted(log["for_user"] for log in h.logs), SALES)
			self.assertEqual(h.logs[0]["subject"], "New reply on quote request QR-0042 from Acme <Lighting>")
			self.assertEqual(h.outbox.record_staff_inbox.call_args.args[5], "reply:MSG-1")

	def test_owned_reply_bells_only_the_owner(self):
		with Harness() as h:
			h.existing_logs = {"bob@illumenate.test"}
			h.module.reply(quote_request(), self.message(), assignee="bob@illumenate.test")
			self.assertEqual(
				[log["for_user"] for log in h.logs], ["bob@illumenate.test"], "every reply rings"
			)
			h.outbox.record_staff_inbox.assert_not_called()

	def test_offer_response_reaches_the_request_owner(self):
		with Harness() as h:
			offer = Record(doctype="ilL-Quote-Offer", name="OFFER-3", response_note="Too high")
			h.module.offer_response(
				offer, quote_request(assigned_to="amy@illumenate.test"), "REQUEST_REVISION"
			)
			self.assertEqual([log["for_user"] for log in h.logs], ["amy@illumenate.test"])
			self.assertEqual(h.logs[0]["subject"], "Acme <Lighting> asked to revise offer OFFER-3")
			self.assertIn("Too high", h.logs[0]["email_content"])


class InboxDelivery(unittest.TestCase):
	def test_shared_inbox_needs_no_portal_account(self):
		with load_service(ROOT + ".portal.outbox") as (module, frappe):
			frappe.utils.validate_email_address = lambda value: "@" in value
			event = Record(
				preference="staff_inbox", reference_type="ilL-Quote-Request", reference_name="QR-1"
			)
			self.assertEqual(module.eligibility(event, "sales@illumenate.lighting")[0], "PENDING")
			self.assertEqual(module.eligibility(event, "")[0], "SKIPPED")


SUBMISSIONS = {
	"portal/quotes.py": ("request_quote", "submitted"),
	"portal/order_review.py": ("capture", "submitted"),
	"portal/order_changes.py": ("submit", "submitted"),
	"portal/accounts.py": ("_new_request", "submitted"),
	"api/portal.py": ("create_support_ticket", "submitted"),
	"portal/offers.py": ("respond", "offer_response"),
	"portal/conversations.py": ("_notify", "reply"),
}


class Wiring(unittest.TestCase):
	def test_every_dealer_submission_routes_to_staff(self):
		package = Path(__file__).resolve().parents[2] / "illumenate_lighting" / "illumenate_lighting"
		for path, (function, call) in SUBMISSIONS.items():
			with self.subTest(function=function):
				tree = ast.parse((package / path).read_text(encoding="utf-8"))
				node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
				calls = {ast.unparse(n.func) for n in ast.walk(node) if isinstance(n, ast.Call)}
				self.assertIn("staff_notifications." + call, calls)


if __name__ == "__main__":
	unittest.main()
