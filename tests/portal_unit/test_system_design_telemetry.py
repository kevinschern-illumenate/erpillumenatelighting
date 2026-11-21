"""Pilot telemetry rows and the details the browser may send (System Designer WP-3.9)."""

import json
import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, load_service

TELEMETRY = ROOT + ".system_design.telemetry"


class Telemetry(unittest.TestCase):
	def test_rows_are_keyed_by_event_name_and_time(self):
		with load_service(TELEMETRY) as (module, frappe):
			key = module.record("opened", "SCH-1", "SYSD-1")
			row = frappe.get_doc.call_args.args[0]
		self.assertEqual(key, frappe.get_doc.return_value.event_key)
		self.assertTrue(row["event_key"].startswith("system_design:opened:SYSD-1:2026-09-25T12:00:00:"))
		self.assertEqual((row["reference_type"], row["reference_name"]), ("ilL-System-Design", "SYSD-1"))
		self.assertEqual(
			json.loads(row["message"]), {"design": "SYSD-1", "event": "opened", "schedule": "SCH-1"}
		)
		self.assertTrue(frappe.get_doc.return_value.flags.notification_service_write)

	def test_a_failed_insert_never_reaches_the_caller(self):
		with load_service(TELEMETRY) as (module, frappe):
			frappe.get_doc.return_value.insert.side_effect = RuntimeError("database away")
			self.assertIsNone(module.record("saved", "SCH-1"))
			frappe.db.rollback.assert_called_once_with(save_point="system_design_telemetry")

	def test_a_get_request_hands_the_row_to_a_background_job(self):
		# Frappe rolls a GET request back, so an inline insert from open_design was always lost.
		with load_service(TELEMETRY) as (module, frappe):
			frappe.local.request = types.SimpleNamespace(method="GET")
			frappe.enqueue = MagicMock()
			key = module.record("opened", "SCH-1", "SYSD-1")
			frappe.get_doc.assert_not_called()
			frappe.db.savepoint.assert_not_called()
			frappe.db.commit.assert_not_called()
			frappe.enqueue.assert_called_once()
			call = frappe.enqueue.call_args
			self.assertEqual(call.args, (module.INSERT_JOB,))
			self.assertEqual(call.kwargs["queue"], "short")
			self.assertFalse(call.kwargs["enqueue_after_commit"])
			row = call.kwargs["row"]
			self.assertEqual(key, row["event_key"])
			self.assertTrue(row["event_key"].startswith("system_design:opened:SYSD-1:2026-09-25T12:00:00:"))
			self.assertEqual(row["preference"], "system_design")
			self.assertEqual(row["subject"], "buyer@example.com")
			self.assertEqual(
				json.loads(row["message"]), {"design": "SYSD-1", "event": "opened", "schedule": "SCH-1"}
			)

			# The job inserts the row as a service write; the job runner commits it.
			frappe.get_doc.return_value.event_key = row["event_key"]
			self.assertEqual(module.insert_event(json.loads(json.dumps(row))), row["event_key"])
			self.assertEqual(frappe.get_doc.call_args.args[0], row)
			self.assertTrue(frappe.get_doc.return_value.flags.notification_service_write)
			frappe.get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)
		self.assertTrue(module.INSERT_JOB.endswith(".system_design.telemetry.insert_event"))

	def test_a_committing_request_inserts_inline(self):
		with load_service(TELEMETRY) as (module, frappe):
			frappe.enqueue = MagicMock()
			for method in ("POST", "PUT", "DELETE", "PATCH"):
				frappe.local.request = types.SimpleNamespace(method=method)
				self.assertTrue(module.request_commits(), method)
			module.record("saved", "SCH-1", "SYSD-1", {"revision": 3})
			frappe.enqueue.assert_not_called()
			frappe.get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)
			frappe.local.request = types.SimpleNamespace(method="GET")
			self.assertFalse(module.request_commits())
			frappe.local.flags = types.SimpleNamespace(commit=True)
			self.assertTrue(module.request_commits())

	def test_a_failed_enqueue_never_reaches_the_caller(self):
		with load_service(TELEMETRY) as (module, frappe):
			frappe.local.request = types.SimpleNamespace(method="GET")
			frappe.enqueue = MagicMock(side_effect=RuntimeError("redis away"))
			frappe.log_error = MagicMock()
			self.assertIsNone(module.record("opened", "SCH-1"))
			# The GET request is rolled back, so the Error Log must be deferred to survive it.
			self.assertTrue(frappe.log_error.call_args.kwargs["defer_insert"])
			frappe.db.rollback.assert_not_called()

	def test_browser_details_are_typed_and_trimmed(self):
		with load_service(TELEMETRY) as (module, _frappe):
			clean = module.clean_details
			self.assertEqual(
				clean("feedback", json.dumps({"rating": 5, "comment": "  Great ", "price": 10})),
				{"rating": 5, "comment": "Great"},
			)
			self.assertEqual(
				clean("check_fixed", {"codes": ["VD_OVER_TARGET"] * 30}), {"codes": ["VD_OVER_TARGET"] * 20}
			)
			self.assertEqual(
				clean("riser_exported", {"kind": "Riser PDF", "sheet": "Letter", "stored": False}),
				{"kind": "Riser PDF", "sheet": "Letter", "stored": False},
			)
			for event, details in (
				("feedback", {"rating": 6}),
				("feedback", {"rating": True}),
				("feedback", {}),
				("check_fixed", {"codes": "VD"}),
				("riser_exported", "[1"),
			):
				with self.assertRaises(module.DesignError, msg=(event, details)) as caught:
					clean(event, details)
				self.assertEqual(caught.exception.code, "INVALID")

	def test_only_browser_events_are_accepted(self):
		with load_service(TELEMETRY) as (module, _frappe):
			with self.assertRaises(module.DesignError) as caught:
				module.log_event("SCH-1", "opened")
		self.assertEqual(caught.exception.code, "INVALID")


if __name__ == "__main__":
	unittest.main()
