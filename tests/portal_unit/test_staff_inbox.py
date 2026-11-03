"""One staff inbox, claim-to-me and the daily overdue digest (plan 7.4)."""

import types
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

NOW = datetime(2026, 11, 10, 9)
SOURCE = Path(__file__).resolve().parents[2] / "illumenate_lighting" / "illumenate_lighting"


def utils(frappe):
	frappe.utils.now_datetime = lambda: NOW
	frappe.utils.now = lambda: "2026-11-10 09:00:00"
	frappe.utils.nowdate = lambda: "2026-11-10"
	frappe.utils.getdate = lambda value: value if isinstance(value, date) and not isinstance(value, datetime) else datetime.fromisoformat(str(value)[:10]).date()
	frappe.utils.get_datetime = lambda value: value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
	frappe.utils.add_to_date = lambda value, hours=0: value + timedelta(hours=hours)


class Inbox(unittest.TestCase):
	def deps(self, allowed=lambda capability: True):
		conversations = types.ModuleType(ROOT + ".portal.conversations")
		conversations._pagination = lambda page, size: (int(page), int(size))
		conversations.PARENTS = (
			"ilL-Product-Verification-Request",
			"ilL-Document-Request",
			"Issue",
			"ilL-Quote-Request",
			"ilL-Order-Intake",
			"ilL-Order-Change",
		)
		conversations.CLOSED = ("Completed", "Closed", "Cancelled", "Resolved")
		staff = types.ModuleType(ROOT + ".portal.staff")
		staff.allowed = MagicMock(side_effect=allowed)
		verification = types.ModuleType(ROOT + ".portal.product_finder.verification")
		verification.staff = lambda: allowed("sales")
		self.commercial = types.ModuleType(ROOT + ".portal.commercial_tasks")
		self.commercial.TYPES = ("ilL-Quote-Request", "ilL-Order-Intake", "ilL-Order-Change", "ilL-Account-Request")
		self.commercial.assign = MagicMock(return_value={"success": True, "modified": "M2"})
		return {
			conversations.__name__: conversations,
			staff.__name__: staff,
			verification.__name__: verification,
			self.commercial.__name__: self.commercial,
		}

	def rows_for(self, frappe, data):
		def get_list(doctype, filters=None, fields=None, **kw):
			self.calls.append((doctype, filters, fields, kw))
			return [Record(row) for row in data.get(doctype, [])]

		self.calls = []
		frappe.get_list = MagicMock(side_effect=get_list)
		frappe.get_all = MagicMock(return_value=[Record(name="CUST-1", customer_name="Acme <Lighting>")])

	def test_due_state_handles_dates_and_datetimes(self):
		with load_service(ROOT + ".portal.queues", self.deps()) as (module, frappe):
			utils(frappe)
			self.assertEqual(module.due_state(None, "due_date"), "none")
			self.assertEqual(module.due_state("2026-11-09", "due_date"), "overdue")
			self.assertEqual(module.due_state("2026-11-10", "due_date"), "due_soon")
			self.assertEqual(module.due_state("2026-11-12", "due_date"), "ok")
			self.assertEqual(module.due_state("2026-11-10 08:00:00", "sla_deadline"), "overdue")
			self.assertEqual(module.due_state("2026-11-11 08:00:00", "sla_deadline"), "due_soon")
			self.assertEqual(module.due_state("2026-11-12 10:00:00", "sla_deadline"), "ok")

	def test_inbox_merges_queues_overdue_first_once_per_record(self):
		with load_service(ROOT + ".portal.queues", self.deps()) as (module, frappe):
			utils(frappe)
			self.rows_for(
				frappe,
				{
					"ilL-Quote-Request": [
						{"name": "QR-2", "customer": "CUST-1", "requested_by": "d@acme.test", "state": "REQUESTED", "assigned_to": None, "due_date": "2026-11-20", "creation": "2026-11-01 00:00:00", "modified": "M1"},
						{"name": "QR-1", "customer": "CUST-1", "state": "UNDER_REVIEW", "assigned_to": "amy@x", "due_date": "2026-11-08", "creation": "2026-11-05 00:00:00", "modified": "M1"},
					],
					"ilL-Document-Request": [
						{"name": "DR-1", "requester_user": "d@acme.test", "status": "Open", "assigned_to": None, "sla_deadline": "2026-11-10 15:00:00", "creation": "2026-11-03 00:00:00", "modified": "M1"},
					],
					"Issue": [
						{"name": "ISS-1", "subject": "Flicker", "status": "Closed", "ill_support_owner": None, "ill_support_due": None, "creation": "2026-11-09 00:00:00", "modified": "M1"},
					],
				},
			)
			result = module.inbox()
			self.assertEqual([row["name"] for row in result["rows"]], ["QR-1", "DR-1", "QR-2", "ISS-1"])
			first = result["rows"][0]
			self.assertEqual(first["due_state"], "overdue")
			self.assertEqual(first["customer_name"], "Acme <Lighting>")
			self.assertEqual(first["age_days"], 5)
			self.assertTrue(first["can_wait"])
			self.assertEqual(result["rows"][1]["dealer_user"], "d@acme.test")
			self.assertEqual(result["rows"][1]["due_state"], "due_soon")
			self.assertFalse(result["rows"][3]["can_wait"], "closed records cannot wait on the dealer")
			# Three drawing queues read ilL-Document-Request, but DR-1 is listed once.
			self.assertEqual(sum(row["name"] == "DR-1" for row in result["rows"]), 1)
			self.assertEqual(sum(call[0] == "ilL-Document-Request" for call in self.calls), 3)
			# The customer display names come from one batched read.
			frappe.get_all.assert_called_once()

	def test_inbox_uses_the_queue_query_and_skips_unsupported_views(self):
		with load_service(ROOT + ".portal.queues", self.deps()) as (module, frappe):
			utils(frappe)
			self.rows_for(frappe, {})
			result = module.inbox("overdue")
			self.assertNotIn("accounts", result["queues"], "account requests have no due date")
			for _doctype, filters, fields, _kw in self.calls:
				self.assertTrue(any(op == "<" for op, *_ in [v for v in filters.values() if isinstance(v, list)]))
				self.assertIn("creation", fields)
			with self.assertRaises(ValueError):
				module.inbox("everything")

	def test_inbox_hides_queues_the_role_cannot_work(self):
		with load_service(ROOT + ".portal.queues", self.deps(lambda capability: capability == "support")) as (module, frappe):
			utils(frappe)
			self.rows_for(frappe, {})
			result = module.inbox()
			self.assertEqual(result["queues"], ["support"])
			self.assertEqual({call[0] for call in self.calls}, {"Issue"})

	def test_inbox_skips_a_queue_without_native_read(self):
		with load_service(ROOT + ".portal.queues", self.deps()) as (module, frappe):
			utils(frappe)
			self.rows_for(frappe, {})
			frappe.has_permission = MagicMock(side_effect=lambda doctype, *a, **kw: doctype != "Issue")
			result = module.inbox()
			self.assertNotIn("support", result["queues"])

	def test_inbox_reports_truncated_queues(self):
		with load_service(ROOT + ".portal.queues", self.deps()) as (module, frappe):
			utils(frappe)
			many = [{"name": f"QR-{i}", "state": "REQUESTED", "creation": "2026-11-01 00:00:00", "modified": "M"} for i in range(module.INBOX_LIMIT + 1)]
			self.rows_for(frappe, {"ilL-Quote-Request": many})
			result = module.inbox()
			self.assertEqual(result["truncated"], ["quotes"])
			self.assertEqual(sum(row["queue"] == "quotes" for row in result["rows"]), module.INBOX_LIMIT)

	def test_claim_commercial_item_reuses_validated_assign_and_keeps_due_date(self):
		with load_service(ROOT + ".portal.queues", self.deps()) as (module, frappe):
			frappe.session = Record(user="amy@illumenate.test")
			frappe.db.get_value.return_value = "2026-11-20"
			result = module.claim("quotes", "QR-1", "M1")
			self.commercial.assign.assert_called_once_with(
				"ilL-Quote-Request", "QR-1", "amy@illumenate.test", "2026-11-20", "M1"
			)
			self.assertEqual(result["assigned_to"], "amy@illumenate.test")

	def test_claim_account_request_passes_no_due_date(self):
		with load_service(ROOT + ".portal.queues", self.deps()) as (module, frappe):
			module.claim("accounts", "AR-1", "M1")
			self.assertIsNone(self.commercial.assign.call_args.args[3])
			frappe.db.get_value.assert_not_called()

	def test_claim_other_item_needs_queue_role_write_permission_and_fresh_modified(self):
		with load_service(ROOT + ".portal.queues", self.deps()) as (module, frappe):
			frappe.session = Record(user="eve@illumenate.test")
			doc = Record(modified="M1", save=MagicMock())
			doc.set = lambda key, value: dict.__setitem__(doc, key, value)
			frappe.get_doc = MagicMock(return_value=doc)
			result = module.claim("support", "ISS-1", "M1")
			self.assertEqual(doc["ill_support_owner"], "eve@illumenate.test")
			doc.save.assert_called_once_with()
			self.assertTrue(result["success"])
			frappe.has_permission.assert_called_with("Issue", "write", doc="ISS-1")
			with self.assertRaises(ValueError):
				module.claim("support", "ISS-1", "STALE")
			frappe.has_permission = MagicMock(return_value=False)
			with self.assertRaises(PermissionError):
				module.claim("support", "ISS-1", "M1")
			with self.assertRaises(ValueError):
				module.claim("publication", "PJ-1", "M1")

	def test_claim_denied_without_queue_role(self):
		with load_service(ROOT + ".portal.queues", self.deps(lambda capability: False)) as (module, frappe):
			with self.assertRaises(PermissionError):
				module.claim("drawings", "DR-1", "M1")
			frappe.get_doc.assert_not_called()

	def test_claim_is_a_post_only_atomic_endpoint(self):
		source = (SOURCE / "portal" / "queues.py").read_text()
		self.assertIn('@frappe.whitelist(methods=["POST"])\n@atomic_build\ndef claim(', source)


class OverdueDigest(unittest.TestCase):
	def run_digest(self, data, staff=("amy@x", "bob@x"), team=("amy@x", "bob@x"), enabled=True, existing=()):
		queues = types.ModuleType(ROOT + ".portal.queues")
		queues.DATE_DUE_FIELDS = ("due_date", "schedule_date")
		queues.QUEUES = {
			"quotes": ("Quote requests", "sales", "ilL-Quote-Request", {"state": ["in", ["REQUESTED"]]}, [], "assigned_to", "due_date"),
			"orders": ("Order review", "sales", "ilL-Order-Intake", {}, [], "assigned_to", "due_date"),
			"order_changes": ("Order changes", "sales", "ilL-Order-Change", {}, [], "assigned_to", "due_date"),
			"verification": ("Product verification", "sales", "ilL-Product-Verification-Request", {}, [], "assigned_to", "due_date"),
			"drawings": ("Drawing responses", "engineering", "ilL-Document-Request", {}, [], "assigned_to", "sla_deadline"),
			"support": ("Support responses", "support", "Issue", {}, [], "ill_support_owner", "ill_support_due"),
		}
		flags = types.ModuleType(ROOT + ".portal.site_flags")
		flags.overdue_digest_enabled = lambda: enabled
		routes = types.ModuleType(ROOT + ".portal.routes")
		routes.desk_path = lambda doctype, name: f"/app/{doctype.lower()}/{name}"
		staff_module = types.SimpleNamespace(CAPABILITIES={"sales": {"S"}, "engineering": {"E"}, "support": {"P"}})
		deps = {
			ROOT + ".portal.staff": staff_module,
			queues.__name__: queues,
			flags.__name__: flags,
			routes.__name__: routes,
		}
		self.logs, self.filters = [], {}
		with load_service(ROOT + ".portal.staff_notifications", deps) as (module, frappe):
			utils(frappe)
			frappe.utils.get_url = lambda path="": "https://erp.test" + path
			frappe.utils.escape_html = lambda value: str(value).replace("<", "&lt;").replace(">", "&gt;")
			frappe.utils.formatdate = lambda value: value
			frappe.utils.format_datetime = lambda value: str(value)

			def get_all(doctype, filters=None, pluck=None, **kw):
				if doctype == "Has Role":
					return list(team)
				if doctype == "User":
					return [user for user in filters["name"][1] if user in staff]
				self.filters[doctype] = filters
				return [Record(row) for row in data.get(doctype, [])]

			frappe.get_all = MagicMock(side_effect=get_all)
			frappe.db.exists.side_effect = lambda doctype, filters: filters["for_user"] in existing
			frappe.get_doc.side_effect = lambda values: Record(values, insert=lambda **kw: self.logs.append(values))
			sent = module.overdue_digest()
		return sent

	def test_owners_get_one_bell_listing_their_items_and_teams_get_unowned(self):
		sent = self.run_digest(
			{
				"ilL-Quote-Request": [
					{"name": "QR-1", "assigned_to": "amy@x", "due_date": "2026-11-01"},
					{"name": "QR-<2>", "assigned_to": None, "due_date": "2026-11-02"},
				],
				"Issue": [{"name": "ISS-1", "ill_support_owner": "gone@x", "ill_support_due": "2026-11-09 10:00:00"}],
			},
			team=("amy@x", "bob@x"),
		)
		self.assertEqual(sent, {"amy@x": 3, "bob@x": 2})
		amy = next(log for log in self.logs if log["for_user"] == "amy@x")
		self.assertEqual(amy["subject"], "Overdue portal work on 2026-11-10")
		self.assertIn("QR-1", amy["email_content"])
		self.assertIn("QR-&lt;2&gt;", amy["email_content"], "record names are escaped")
		self.assertNotIn("QR-<2>", amy["email_content"])
		self.assertIn("ISS-1", amy["email_content"], "a disabled owner's item goes to the team")
		self.assertEqual(self.filters["ilL-Quote-Request"]["due_date"], ["<", "2026-11-10"])
		self.assertEqual(self.filters["ilL-Quote-Request"]["state"], ["in", ["REQUESTED"]])
		self.assertEqual(self.filters["Issue"]["ill_support_due"], ["<", "2026-11-10 09:00:00"])

	def test_second_run_the_same_day_rings_nobody(self):
		data = {"ilL-Quote-Request": [{"name": "QR-1", "assigned_to": "amy@x", "due_date": "2026-11-01"}]}
		self.assertEqual(self.run_digest(data, existing=("amy@x",)), {})
		self.assertEqual(self.logs, [])

	def test_kill_switch_and_nothing_overdue_send_nothing(self):
		data = {"ilL-Quote-Request": [{"name": "QR-1", "assigned_to": "amy@x", "due_date": "2026-11-01"}]}
		self.assertEqual(self.run_digest(data, enabled=False), {})
		self.assertEqual(self.run_digest({}), {})
		self.assertEqual(self.logs, [])

	def test_long_lists_are_capped(self):
		rows = [{"name": f"QR-{i}", "assigned_to": "amy@x", "due_date": "2026-11-01"} for i in range(60)]
		self.run_digest({"ilL-Quote-Request": rows})
		body = self.logs[0]["email_content"]
		self.assertEqual(body.count("<li>"), 50)
		self.assertIn("and 10 more", body)
		self.assertIn("60 portal request(s)", body)

	def test_digest_is_scheduled_daily(self):
		hooks = (SOURCE.parent / "hooks.py").read_text()
		self.assertIn("portal.staff_notifications.overdue_digest", hooks.split('"daily"')[1].split("]")[0])


if __name__ == "__main__":
	unittest.main()
