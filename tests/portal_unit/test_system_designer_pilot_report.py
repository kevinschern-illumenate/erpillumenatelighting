"""System Designer Pilot report aggregation (WP-3.9)."""

import json
import unittest
from datetime import datetime

from test_services import ROOT, Record, load_service

REPORT = ROOT + ".report.system_designer_pilot.system_designer_pilot"


def event(name, minute, user="dealer@example.com", **details):
	message = {"event": name, "schedule": "SCH-1", "design": "SYSD-1", **details}
	return Record(
		event_key=f"system_design:{name}:SYSD-1:2026-10-09T10:{minute:02d}:00:abc",
		message=json.dumps(message),
		subject=user,
		creation=datetime(2026, 10, 9, 10, minute),
	)


class PilotRows(unittest.TestCase):
	def test_one_row_per_schedule_with_time_to_riser_and_rating(self):
		events = [
			event("opened", 0),
			event("check_fixed", 5, codes=["VD_OVER_TARGET", "PSU_OVERLOAD"]),
			event("saved", 10),
			event("riser_exported", 22, kind="Riser PDF", stored=True),
			event("riser_exported", 25, kind="Riser DXF ZIP", stored=False),
			event("feedback", 26, rating=4, comment="Clear"),
			event("opened", 40, user="ae@illumenate.com"),
			Record(
				event_key="system_design:opened:x",
				message="not json",
				subject="x",
				creation=datetime(2026, 10, 9),
			),
		]
		with load_service(REPORT) as (module, _frappe):
			[row] = module.pilot_rows(events, {"SCH-1": "Bright Dealer Co"})
		self.assertEqual(
			{
				key: row[key]
				for key in ("customer", "design", "users", "opened", "saved", "riser_exported", "check_fixed")
			},
			{
				"customer": "Bright Dealer Co",
				"design": "SYSD-1",
				"users": 2,
				"opened": 2,
				"saved": 1,
				"riser_exported": 2,
				"check_fixed": 2,
			},
		)
		self.assertEqual((row["minutes_to_riser"], row["rating"], row["comments"]), (22.0, 4, "Clear"))


if __name__ == "__main__":
	unittest.main()
