"""UI-4: portal pages read status labels and badge classes from one vocabulary."""

import unittest

from test_services import ROOT, load_service


class StatusVocabulary(unittest.TestCase):
	def service(self):
		context = load_service(ROOT + ".portal.status")
		module, _frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		return module

	def test_every_schedule_status_has_a_label_and_class_for_page_scripts(self):
		module = self.service()
		statuses = module.schedule_status_map()
		for status in ("DRAFT", "READY", "QUOTED", "ORDER_REQUESTED", "ORDERED", "ISSUE", "CLOSED"):
			with self.subTest(status=status):
				self.assertTrue(statuses[status]["label"])
				self.assertNotEqual(statuses[status]["label"], status)
				self.assertTrue(statuses[status]["css"])

	def test_export_statuses_cover_every_job_state(self):
		exports = self.service().export_status_map()
		self.assertEqual(set(exports), {"QUEUED", "RUNNING", "COMPLETE", "INCOMPLETE", "FAILED"})
		self.assertEqual(exports["FAILED"], {"label": "Failed", "css": "danger"})

	def test_project_and_verification_states_never_show_raw_codes(self):
		module = self.service()
		self.assertEqual(
			(module.project_status_label("ON_HOLD"), module.project_status_class("ON_HOLD")),
			("On hold", "warning"),
		)
		self.assertEqual(module.project_status_class("SOMETHING_NEW"), "secondary")
		self.assertEqual(module.verification_status("UNDER_REVIEW"), ("Under review", "info"))
		self.assertEqual(module.verification_status("INFORMATION_NEEDED"), ("Needs your reply", "warning"))
		self.assertEqual(module.verification_status(None), ("", "secondary"))


if __name__ == "__main__":
	unittest.main()
