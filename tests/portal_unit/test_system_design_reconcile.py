"""Reconcile a saved design with its schedule (System Designer H8.4, WP-2.5).

The committed ``fixtures/reconcile/case.json`` starts from the WP-2.3 open-design payload, changes the
schedule once per diff category, and records the fingerprints and diff Python computes; the
TypeScript suite recomputes both and applies the diff to design runs. Regenerate after a deliberate
change with ``python3 -B tests/portal_unit/test_system_design_reconcile.py --write``.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

from test_services import ROOT, load_service

RECONCILE = ROOT + ".system_design.reconcile"
FIXTURES = Path(__file__).resolve().parents[2] / "tools/system_designer/packages/core-schemas/fixtures"
OPENED = json.loads((FIXTURES / "open-design/expected.json").read_text(encoding="utf-8"))
CASE = FIXTURES / "reconcile/case.json"

# Runs the saved design holds for the group line that the schedule then drops.
DESIGN_RUNS = [
	{"key": "d1group:1:1", "lineKey": "d1group", "assignment": {"equipmentId": "PS-01", "port": "OUT 1"}},
	{"key": "d1group:1:2", "lineKey": "d1group"},
	{"key": "a1linear:1:1", "lineKey": "a1linear", "assignment": {"equipmentId": "PS-02", "port": "OUT 1"}},
]


def after_schedule():
	"""One change per H8.4 category, plus a dealer-data change on a third-party line."""
	lines = copy.deepcopy(OPENED["lines"])
	builds = copy.deepcopy(OPENED["builds"])
	by_key = {line["key"]: line for line in lines}
	by_key["a1linear"]["qty"] = 3
	by_key["a1linear"]["location"] = "Moved"  # not a fingerprint field
	builds["ilL-Configured-Tape-Neon"]["ILL-CTN-00001"]["configHash"] = "changed-config"
	by_key["e1other"]["thirdParty"]["wattsEach"] = 14.5
	by_key["j1wire"]["qty"] = 9  # write-back output: ignored
	lines = [line for line in lines if line["key"] != "d1group"]
	added = copy.deepcopy(by_key["e1other"])
	added.update({"key": "n1new", "lineKey": "n1new", "lineId": "N1", "idx": 11, "qty": 2})
	added["thirdParty"]["wattsEach"] = 10
	lines.append(added)
	return lines, builds


def build_case(module):
	stored = module.fingerprints(OPENED["lines"], OPENED["builds"])
	lines, builds = after_schedule()
	return {
		"after": {"lines": lines, "builds": builds},
		"stored": stored,
		"design_runs": DESIGN_RUNS,
		"diff": module.diff(stored, lines, builds, DESIGN_RUNS),
	}


class Reconcile(unittest.TestCase):
	def setUp(self):
		self.context = load_service(RECONCILE)
		self.module, _frappe = self.context.__enter__()

	def tearDown(self):
		self.context.__exit__(None, None, None)

	def test_committed_case_matches(self):
		expected = json.loads(CASE.read_text(encoding="utf-8"))
		self.assertEqual(json.loads(json.dumps(build_case(self.module))), expected)

	def test_each_category(self):
		result = build_case(self.module)["diff"]
		self.assertEqual(result["added"], [{"key": "n1new", "lineId": "N1"}])
		self.assertEqual(
			result["removed"],
			[
				{
					"key": "d1group",
					"runs": ["d1group:1:1", "d1group:1:2"],
					"assignments": [{"runKey": "d1group:1:1", "equipmentId": "PS-01", "port": "OUT 1"}],
				}
			],
		)
		self.assertEqual(
			result["changed"], [{"key": "b1tape", "lineId": "B1"}, {"key": "e1other", "lineId": "E1"}]
		)
		self.assertEqual(result["qty"], [{"key": "a1linear", "lineId": "A1", "from": 2, "to": 3}])
		self.assertFalse(result["in_sync"])

	def test_unchanged_schedule_is_in_sync(self):
		stored = self.module.fingerprints(OPENED["lines"], OPENED["builds"])
		self.assertNotIn("j1wire", stored)
		self.assertEqual(stored["a1linear"]["qty"], 2)
		result = self.module.diff(stored, OPENED["lines"], OPENED["builds"])
		self.assertTrue(result["in_sync"])

	def test_quantity_and_config_change_together_is_a_change(self):
		stored = self.module.fingerprints(OPENED["lines"], OPENED["builds"])
		lines, builds = copy.deepcopy(OPENED["lines"]), copy.deepcopy(OPENED["builds"])
		lines[0]["qty"] = 5
		builds["ilL-Configured-Fixture"]["ILL-CF-LINEAR"]["configHash"] = "other"
		result = self.module.diff(stored, lines, builds)
		self.assertEqual([item["key"] for item in result["changed"]], ["a1linear"])
		self.assertEqual(result["qty"], [])

	def test_legacy_fingerprint_strings_are_read(self):
		stored = {
			key: value["fingerprint"]
			for key, value in self.module.fingerprints(OPENED["lines"], OPENED["builds"]).items()
		}
		lines = copy.deepcopy(OPENED["lines"])
		lines[0]["qty"] = 4
		result = self.module.diff(stored, lines, OPENED["builds"])
		self.assertEqual([item["key"] for item in result["changed"]], ["a1linear"])
		self.assertTrue(self.module.diff(stored, OPENED["lines"], OPENED["builds"])["in_sync"])


def write_case():
	with load_service(RECONCILE) as (module, _frappe):
		CASE.write_text(
			json.dumps(build_case(module), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
			encoding="utf-8",
		)


if __name__ == "__main__":
	if "--write" in sys.argv:
		write_case()
	else:
		unittest.main()
