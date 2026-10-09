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


class Comments(unittest.TestCase):
	def test_pins_are_fractions_of_a_sheet_or_an_entity(self):
		with load_service(REVIEW) as (module, _frappe):
			self.assertIsNone(module.clean_anchor(None))
			self.assertEqual(
				module.clean_anchor({"sheet": "E-1", "x": 0.25, "y": 0.123456, "extra": "dropped"}),
				'{"sheet":"E-1","x":0.25,"y":0.1235}',
			)
			self.assertEqual(module.clean_anchor('{"entityRef": "PS-1"}'), '{"entityRef":"PS-1"}')
			for bad in ({"x": 1.5, "y": 0}, {"x": 0.5}, {"x": True, "y": 0}, "[1]", "nope"):
				with self.assertRaises(module.DesignError, msg=bad):
					module.clean_anchor(bad)


class Overrides(unittest.TestCase):
	def test_an_override_replaces_the_earlier_one_for_the_same_check(self):
		with load_service(REVIEW) as (module, _frappe):
			earlier = [
				{"code": "PSU_OVERLOAD", "entityRef": "PS-1", "kind": "acknowledge", "reason": "old"},
				{"code": "VD_OVER_TARGET", "entityRef": "load:a", "kind": "acknowledge", "reason": "keep"},
			]
			result = module.add_override(earlier, "PSU_OVERLOAD", "PS-1", " Field verified ", "ae@x.com", "T")
			self.assertEqual([item["code"] for item in result], ["VD_OVER_TARGET", "PSU_OVERLOAD"])
			self.assertEqual(
				result[-1],
				{
					"code": "PSU_OVERLOAD",
					"entityRef": "PS-1",
					"kind": "staff-override",
					"reason": "Field verified",
					"by": "ae@x.com",
					"at": "T",
				},
			)
			with self.assertRaises(module.DesignError):
				module.add_override([], "PSU_OVERLOAD", "PS-1", "no", "ae@x.com", "T")


if __name__ == "__main__":
	unittest.main()
