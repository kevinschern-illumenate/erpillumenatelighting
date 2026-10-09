"""Design review requests: reviewer rotation and the server's error gate (System Designer WP-4.2)."""

import unittest

from test_services import ROOT, load_service

REVIEW = ROOT + ".system_design.review"


class Reviewers(unittest.TestCase):
	def test_round_robin_follows_name_order_and_wraps(self):
		with load_service(REVIEW) as (module, _frappe):
			team = ["c@x.com", "a@x.com", "b@x.com"]
			self.assertEqual(module.next_reviewer(team, None), "a@x.com")
			self.assertEqual(module.next_reviewer(team, "a@x.com"), "b@x.com")
			self.assertEqual(module.next_reviewer(team, "c@x.com"), "a@x.com")
			# A reviewer who left the team: the next name after theirs.
			self.assertEqual(module.next_reviewer(team, "ab@x.com"), "b@x.com")
			self.assertEqual(module.next_reviewer(team, "z@x.com"), "a@x.com")
			self.assertIsNone(module.next_reviewer([], "a@x.com"))

	def test_manual_assignment_names_nobody(self):
		with load_service(REVIEW) as (module, frappe):
			self.assertIsNone(module.assign_reviewer({"reviewer_assignment": "Manual"}))
			frappe.get_all.assert_not_called()


class ServerErrors(unittest.TestCase):
	def test_errors_block_unless_an_applications_engineer_overrode_them(self):
		with load_service(REVIEW) as (module, _frappe):
			design = {
				"overrides": [
					{"code": "PSU_OVERLOAD", "entityRef": "PS-2", "kind": "staff-override"},
					{"code": "VOLTAGE_MISMATCH", "entityRef": "PS-3", "kind": "acknowledge"},
				]
			}
			messages = [
				"PSU_OVERLOAD|PS-1",
				"PSU_OVERLOAD|PS-2",
				"VOLTAGE_MISMATCH|PS-3",
				"PSU_ABOVE_DERATE|PS-1",
				"DATA_BY_DEALER|TP1",
			]
			self.assertEqual(
				module.server_errors(messages, design), ["PSU_OVERLOAD|PS-1", "VOLTAGE_MISMATCH|PS-3"]
			)

	def test_counts_must_be_whole_numbers(self):
		with load_service(REVIEW) as (module, _frappe):
			self.assertEqual(module.count("3", "error_count"), 3)
			self.assertEqual(module.count(None, "error_count"), 0)
			for bad in ("x", -1):
				with self.assertRaises(module.DesignError):
					module.count(bad, "error_count")


if __name__ == "__main__":
	unittest.main()
