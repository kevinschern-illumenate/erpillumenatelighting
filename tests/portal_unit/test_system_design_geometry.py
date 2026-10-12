"""SH01 cross-section seed and the cross_section_json rules (System Designer WP-1.5)."""

import json
import re
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, load_service

REPO = Path(__file__).resolve().parents[2]
GEOMETRY = ROOT + ".system_design.geometry"


class Sh01Seed(unittest.TestCase):
	def test_seed_is_the_visualizer_constant(self):
		html = (REPO / "tools/system_designer/reference/led-tape-system-visualizer.html").read_text(
			encoding="utf-8"
		)
		constant = json.loads(re.search(r"^const CAD_SH01 = (\{.*?\});$", html, re.M).group(1))
		with load_service(GEOMETRY) as (geometry, _frappe):
			self.assertEqual(geometry.load_sh01_seed(), constant)
			self.assertEqual(geometry.cross_section_problems(json.dumps(constant)), [])

	def test_outline_rules(self):
		with load_service(GEOMETRY) as (geometry, _frappe):
			problems = geometry.cross_section_problems
			self.assertEqual(problems(None), [])
			self.assertEqual(problems(""), [])
			self.assertEqual(problems("{nope"), ["Cross-section outlines must be valid JSON"])
			self.assertEqual(problems("[1, 2]"), ["Cross-section outlines must be a JSON object"])
			self.assertEqual(
				problems('{"lens": [0, 0, 1, 0, 1, 1]}'), ["Cross-section outlines need a body outline"]
			)
			self.assertEqual(len(problems('{"body": [0, 0, 1, 0, 1]}')), 1)
			self.assertEqual(len(problems('{"body": [0, 0, 1, 0, 1, 1], "clip": [0, "a", 1, 0, 1, 1]}')), 1)
			self.assertEqual(problems({"body": [0, 0, 1, 0, 1, 1], "swivelPlan": {"w": 1}}), [])


class Sh01Patch(unittest.TestCase):
	def run_patch(self, stored):
		with load_service("illumenate_lighting.patches.seed_sh01_cross_section") as (patch, frappe):
			frappe.db.has_column.return_value = True
			frappe.get_all.side_effect = lambda doctype, filters, pluck: (
				["SH01-PROFILE"] if "family" in filters else ["SH01-PROFILE", "SH01-ALT"]
			)
			frappe.db.exists.return_value = True
			frappe.db.get_value.side_effect = lambda doctype, name, field: (
				"SH01-DEFAULT" if doctype == "ilL-Fixture-Template" else stored.get(name)
			)
			frappe.db.set_value = MagicMock()
			patch.execute()
			return frappe.db.set_value.call_args_list

	def test_fills_only_empty_sh01_profiles(self):
		calls = self.run_patch({"SH01-ALT": '{"body": [1, 2, 3, 4, 5, 6]}'})
		self.assertEqual([c.args[1] for c in calls], ["SH01-DEFAULT", "SH01-PROFILE"])
		for call in calls:
			self.assertEqual(call.args[2], "cross_section_json")
			self.assertEqual(sorted(json.loads(call.args[3]))[:3], ["body", "clip", "lens"])
			self.assertEqual(call.kwargs, {"update_modified": False})

	def test_rerun_changes_nothing(self):
		seeded = dict.fromkeys(["SH01-ALT", "SH01-DEFAULT", "SH01-PROFILE"], '{"body": []}')
		self.assertEqual(self.run_patch(seeded), [])


if __name__ == "__main__":
	unittest.main()
