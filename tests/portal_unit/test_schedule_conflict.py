"""Plan 3.12: a refused stale edit says who saved the schedule and when."""

import types
import unittest

from test_services import ROOT, Record, load_service

LOADED = "2026-11-03 10:00:00.000001"
SAVED = "2026-11-03 10:05:00.000002"


class ConflictNotice(unittest.TestCase):
	def schedule(self, **values):
		return Record({"name": "S1", "modified": SAVED, "modified_by": "pat@example.com", **values})

	def test_stale_edit_raises_with_the_modifier_name_and_time(self):
		with load_service(ROOT + ".portal.schedule_lines") as (module, frappe):
			frappe.db.get_value.return_value = "Pat Smith"
			frappe.utils.format_datetime = lambda value: "Nov 3, 10:05"
			frappe.local.response = {}
			with self.assertRaisesRegex(module.StaleScheduleError, "changed since you opened it") as caught:
				module.require_fresh(self.schedule(), LOADED)
			conflict = {"modified": SAVED, "modified_display": "Nov 3, 10:05", "modified_by_name": "Pat Smith"}
			self.assertEqual(caught.exception.conflict, conflict)
			self.assertIsInstance(caught.exception, frappe.ValidationError, "old error handling still applies")
			self.assertEqual(frappe.local.response["conflict"], conflict, "thrown responses carry it too")
			frappe.db.get_value.assert_called_once_with("User", "pat@example.com", "full_name")
			self.assertNotIn("pat@example.com", str(conflict), "never the email address")

	def test_fresh_or_unchecked_edits_pass(self):
		with load_service(ROOT + ".portal.schedule_lines") as (module, frappe):
			module.require_fresh(self.schedule(), SAVED)
			module.require_fresh(self.schedule(), None)
			frappe.db.get_value.assert_not_called()

	def test_unknown_modifier_and_missing_formatter_fall_back(self):
		with load_service(ROOT + ".portal.schedule_lines") as (module, frappe):
			frappe.db.get_value.return_value = None
			details = module.conflict_details(self.schedule(modified_by=None))
			self.assertEqual(details, {"modified": SAVED, "modified_display": SAVED, "modified_by_name": "another user"})
			frappe.utils.format_datetime = lambda value: 1 / 0
			self.assertEqual(module.conflict_details(self.schedule())["modified_display"], SAVED)
			with self.assertRaises(module.StaleScheduleError):
				module.require_fresh(self.schedule(), LOADED)  # no frappe.local.response: still refused

	def test_safe_error_adds_conflict_and_keeps_the_old_keys(self):
		deps = {ROOT + ".portal.staff": types.SimpleNamespace(allowed=lambda c: False)}
		with load_service(ROOT + ".api.portal", deps) as (api, frappe):
			frappe.log_error = lambda **kwargs: None
			frappe.get_traceback = lambda: ""
			frappe.utils.strip_html = lambda value: value
			error = frappe.ValidationError("This schedule changed since you opened it.")
			error.conflict = {"modified_by_name": "Pat Smith"}
			result = api._safe_error(error, "prefix")
			self.assertEqual(
				{key: result[key] for key in ("success", "error", "error_code")},
				{"success": False, "error": "This schedule changed since you opened it.", "error_code": "validation_error"},
			)
			self.assertEqual(result["conflict"], {"modified_by_name": "Pat Smith"})
			self.assertNotIn("conflict", api._safe_error(frappe.ValidationError("Other"), "prefix"))


if __name__ == "__main__":
	unittest.main()
