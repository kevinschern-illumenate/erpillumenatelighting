"""Plan 3.11: the schedule activity timeline shows dealer-visible history only."""

import json
import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

VERSIONS = [
	Record(
		name="V3",
		owner="dealer@example.com",
		creation="2026-09-25 12:03:00",
		data=json.dumps(
			{
				"changed": [["status", "DRAFT", "READY"], ["status_note", "", "internal: credit hold"]],
				"row_changed": [
					["lines", 0, "r1", [["qty", 1, 4], ["location", "", "Lobby"], ["internal_cost", 1, 2]]],
					["lines", 1, "gone", [["notes", "a", "b"]]],
				],
			}
		),
	),
	Record(
		name="V2",
		owner="staff@example.com",
		creation="2026-09-25 12:02:00",
		data=json.dumps({"changed": [["is_private", 0, 1], ["collaborators", "", "x"]]}),
	),
	Record(
		name="V1",
		owner="dealer@example.com",
		creation="2026-09-25 12:01:00",
		data=json.dumps(
			{
				"added": [["lines", {"line_id": "A1", "idx": 1}], ["collaborators", {"user": "x"}]],
				"removed": [["lines", {"idx": 2}]],
				"changed": [["schedule_name", "Old", "New <b>name</b>"], ["is_locked", 0, 1]],
			}
		),
	),
	Record(name="V0", owner="dealer@example.com", creation="2026-09-25 12:00:00", data="not json"),
]
EVENTS = [
	Record(name="E1", subject="Quote ready: A &amp; B <b>x</b>", preference="notify_quotes", creation="2026-09-25 12:04:00"),
	Record(name="E2", subject="Staff only", preference="staff_inbox", creation="2026-09-25 12:05:00"),
]
EXPORTS = [
	Record(name="X1", export_type="PDF_PRICED", status="COMPLETED", requested_by="dealer@example.com", created_on="2026-09-25 12:06:00"),
	Record(name="X2", export_type="CSV_NO_PRICE", status="COMPLETED", requested_by="dealer@example.com", created_on="2026-09-25 11:00:00"),
]


class ScheduleActivity(unittest.TestCase):
	def setUp(self):
		self.enabled = True
		self.priced = True
		self.schedule = Record(name="S1", lines=[Record(name="r1", line_id="A1")])
		self.contexts = []

		def schedule_context(name, write=False, lock=False):
			self.contexts.append((name, write, lock))
			return self.schedule

		self.extras = {
			ROOT + ".portal.site_flags": types.SimpleNamespace(activity_timeline_enabled=lambda: self.enabled),
			ROOT + ".portal.configuration": types.SimpleNamespace(schedule_context=schedule_context),
			ROOT + ".portal.status": types.SimpleNamespace(schedule_status_label=lambda status: status.title()),
			ROOT + ".portal.notifications": types.SimpleNamespace(
				PREFERENCE_DEFAULTS={"notify_orders": True, "notify_quotes": True, "notify_marketing": False}
			),
			ROOT + ".api.exports": types.SimpleNamespace(_check_pricing_permission=lambda: self.priced),
		}

	def run_activity(self, *args, **kwargs):
		with load_service(ROOT + ".portal.schedule_activity", self.extras) as (module, frappe):
			self.frappe = frappe

			def get_all(doctype, filters=None, fields=None, order_by=None, limit_page_length=None):
				if doctype == "Version":
					return VERSIONS
				if doctype == "ilL-Portal-Event":
					# The query only asks for dealer preferences; E2 also proves the defensive filter.
					self.event_filters = filters
					return EVENTS
				if doctype == "ilL-Export-Job":
					self.export_filters = filters
					return [job for job in EXPORTS if self.priced or job.export_type != "PDF_PRICED"]
				if doctype == "User":
					return [Record(name="dealer@example.com", full_name="Dana Dealer")]
				return []

			frappe.get_all = MagicMock(side_effect=get_all)
			return module.schedule_activity("S1", *args, **kwargs)

	def kinds(self, result):
		return [(entry["kind"], entry["title"]) for entry in result["entries"]]

	def test_merges_versions_portal_events_and_exports_newest_first(self):
		result = self.run_activity(limit=50)
		self.assertEqual(self.contexts, [("S1", False, False)], "read access is checked")
		self.assertEqual(
			self.kinds(result),
			[
				("export", "Export: PDF with pricing"),
				("notice", "Quote ready: A & B x"),
				("status", "Status changed to Ready"),
				("line_edited", "2 line(s) edited"),
				("renamed", "Renamed to New name"),
				("locked", "Version locked"),
				("line_added", "1 line(s) added"),
				("line_removed", "1 line(s) removed"),
				("export", "Export: CSV without pricing"),
			],
		)
		edited = result["entries"][3]
		self.assertEqual(edited["detail"], "A1: Quantity 1 → 4, Location (empty) → Lobby; Line 2: Notes a → b")
		self.assertEqual((edited["by_name"], edited["at"]), ("Dana Dealer", "2026-09-25 12:03:00"))
		self.assertEqual(result["entries"][6]["detail"], "A1")
		self.assertEqual(result["entries"][7]["detail"], "Line 2")
		self.assertEqual(result["entries"][1]["by_name"], "")
		self.assertEqual((result["has_more"], result["next_start"]), (False, None))

	def test_internal_fields_staff_events_and_emails_never_appear(self):
		text = json.dumps(self.run_activity(limit=50))
		for hidden in ("credit hold", "internal_cost", "is_private", "collaborators", "Staff only", "@example.com"):
			self.assertNotIn(hidden, text)
		self.assertEqual(self.event_filters["preference"], ["in", ["notify_marketing", "notify_orders", "notify_quotes"]])
		self.assertEqual(self.event_filters["reference_name"], "S1")

	def test_priced_exports_are_hidden_without_pricing_permission(self):
		self.priced = False
		result = self.run_activity(limit=50)
		self.assertEqual(self.export_filters["export_type"], ["not in", ["PDF_PRICED", "CSV_PRICED"]])
		self.assertNotIn("Export: PDF with pricing", [title for _kind, title in self.kinds(result)])

	def test_pages_are_capped(self):
		first = self.run_activity(limit=3)
		self.assertEqual((len(first["entries"]), first["has_more"], first["next_start"]), (3, True, 3))
		second = self.run_activity(start=first["next_start"], limit=3)
		self.assertEqual(second["entries"][0]["title"], "2 line(s) edited")
		self.assertEqual(len(self.run_activity(limit=500)["entries"]), 9, "the page size is capped at 50")
		self.assertEqual(self.run_activity(start="x")["entries"][0]["kind"], "export")
		self.assertEqual(self.run_activity(start=10_000)["entries"], [], "start is capped too")

	def test_kill_switch_and_guest(self):
		self.enabled = False
		with self.assertRaisesRegex(ValueError, "turned off"):
			self.run_activity()
		self.enabled = True
		with load_service(ROOT + ".portal.schedule_activity", self.extras) as (module, frappe):
			frappe.session = Record(user="Guest")
			with self.assertRaises(PermissionError):
				module.schedule_activity("S1")
		self.assertEqual(self.contexts, [])


if __name__ == "__main__":
	unittest.main()
