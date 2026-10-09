"""Schedule and project page integration of the System Designer (WP-4.5)."""

import types
import unittest

from test_services import ROOT, Record, load_service

PAGES = ROOT + ".system_design.portal_pages"


def designer(enabled=True):
	return {ROOT + ".system_design.settings": types.SimpleNamespace(is_enabled_for=lambda: enabled)}


class ReviewChip(unittest.TestCase):
	def test_states(self):
		with load_service(PAGES) as (module, _frappe):
			chip = module.review_chip
			self.assertIsNone(chip({"required": False, "satisfied": True}))
			self.assertIsNone(chip(None))
			self.assertEqual(chip({"required": True, "satisfied": False})["label"], "Review required")
			self.assertEqual(chip({"required": True, "satisfied": False}, "In Review")["label"], "In review")
			self.assertEqual(chip({"required": True, "satisfied": True})["label"], "Review approved")
			self.assertEqual(
				chip({"required": True, "satisfied": True, "override": {"by": "a"}})["label"],
				"Review overridden",
			)


class ProjectDesigns(unittest.TestCase):
	def test_current_designs_of_the_schedules_shown_only(self):
		with load_service(PAGES, designer()) as (module, frappe):
			frappe.db.exists.return_value = True
			frappe.get_all.return_value = [
				Record(
					name="SYSD-2",
					title="Kitchen design",
					fixture_schedule="SCH-1",
					schedule_version=2,
					revision="B",
					status="In Review",
					modified="2026-10-09",
				),
				Record(
					name="SYSD-1",
					title="Old version",
					fixture_schedule="SCH-1",
					schedule_version=1,
					revision="A",
					status="Approved",
					modified="2026-10-01",
				),
			]
			schedules = [Record(name="SCH-1", schedule_name="Kitchen", version=2)]
			designs = module.project_designs(schedules)
			self.assertEqual(
				[(row["name"], row["status"], row["tone"], row["url"]) for row in designs],
				[("SYSD-2", "In Review", "info", "/portal/schedules/SCH-1/design")],
			)
			filters = frappe.get_all.call_args.kwargs["filters"]
			self.assertEqual(filters, {"fixture_schedule": ["in", ["SCH-1"]], "is_current": 1})

	def test_hidden_when_the_designer_is_off(self):
		with load_service(PAGES, designer(False)) as (module, frappe):
			self.assertIsNone(module.project_designs([Record(name="SCH-1", version=1)]))
			frappe.get_all.assert_not_called()


if __name__ == "__main__":
	unittest.main()
