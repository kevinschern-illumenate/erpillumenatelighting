"""Schedule line actions address lines by key and refuse stale revisions (REL-3)."""

import types
import unittest
from unittest.mock import MagicMock

from test_product_finder_content import FakeDocument
from test_services import ROOT, Record, load_service

LOADED = "2026-10-14 03:00:00.000001"


class LineKeys(unittest.TestCase):
	def call(self, endpoint, *args, modified=LOADED, locked=0, **kwargs):
		deps = {
			ROOT + ".portal.staff": types.SimpleNamespace(allowed=lambda c: False),
			ROOT
			+ ".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule": types.SimpleNamespace(
				has_permission=lambda *a: True
			),
		}
		with load_service(ROOT + ".api.portal", deps) as (api, frappe):
			# Another tab inserted line X before A since this page loaded.
			self.lines = [FakeDocument(idx=i, line_key=key, line_id=key) for i, key in enumerate("XABC", 1)]
			schedule = Record(
				name="S",
				status="DRAFT",
				is_locked=locked,
				modified=modified,
				lines=self.lines,
				save=MagicMock(),
				duplicate_line=MagicMock(
					side_effect=lambda idx: self.lines.append(FakeDocument(line_key="A2")) or 4
				),
				move_line=MagicMock(return_value=0),
			)
			self.schedule = schedule
			frappe.get_doc.return_value = schedule
			frappe.db.exists.return_value = True
			frappe.log_error = MagicMock()
			frappe.get_traceback = MagicMock(return_value="")
			frappe.utils.strip_html = lambda value: value
			return getattr(api, endpoint)("S", *args, **kwargs)

	def keys(self):
		return [line.line_key for line in self.lines]

	def test_delete_by_key_removes_that_line_even_after_a_shift(self):
		result = self.call("delete_schedule_line", line_idx=1, line_key="B", expected_modified=LOADED)
		self.assertTrue(result["success"], result)
		self.assertEqual(self.keys(), ["X", "A", "C"])
		self.assertEqual(result["modified"], LOADED)

	def test_stale_revision_is_refused_without_writing(self):
		result = self.call(
			"delete_schedule_line", line_key="B", expected_modified=LOADED, modified="2026-10-14 03:05:00"
		)
		self.assertFalse(result["success"])
		self.assertIn("changed since you opened it", result["error"])
		self.assertEqual(self.keys(), ["X", "A", "B", "C"])
		self.schedule.save.assert_not_called()

	def test_unknown_key_never_falls_back_to_the_index(self):
		result = self.call("delete_schedule_line", line_idx=0, line_key="GONE")
		self.assertFalse(result["success"])
		self.assertEqual(self.keys(), ["X", "A", "B", "C"])

	def test_legacy_index_still_works(self):
		result = self.call("delete_schedule_line", line_idx=3)
		self.assertTrue(result["success"], result)
		self.assertEqual(self.keys(), ["X", "A", "B"])

	def test_update_duplicate_and_move_resolve_keys(self):
		result = self.call("update_schedule_line", line_key="C", line_data={"location": "Lobby"})
		self.assertTrue(result["success"], result)
		self.assertEqual(self.lines[3].location, "Lobby")
		result = self.call("duplicate_schedule_line", line_key="A")
		self.assertEqual((result["new_line_idx"], result["new_line_key"]), (4, "A2"))
		self.schedule.duplicate_line.assert_called_once_with(1)
		result = self.call("move_schedule_line", line_key="C", to_line_key="X")
		self.assertTrue(result["success"], result)
		self.schedule.move_line.assert_called_once_with(3, 0)

	def test_duplicate_refuses_a_locked_version_up_front(self):
		result = self.call("duplicate_schedule_line", line_key="A", locked=1)
		self.assertFalse(result["success"])
		self.assertIn("locked", result["error"])
		self.schedule.duplicate_line.assert_not_called()


if __name__ == "__main__":
	unittest.main()
