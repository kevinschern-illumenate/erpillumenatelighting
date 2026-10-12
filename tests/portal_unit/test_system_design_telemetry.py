"""Pilot telemetry rows and the details the browser may send (System Designer WP-3.9)."""

import json
import unittest

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
