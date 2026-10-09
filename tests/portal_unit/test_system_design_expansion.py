"""Schedule lines → builds and readiness (System Designer H8.1, WP-2.3), and the D4 gate answer.

The TEST records in ``packages/core-schemas/fixtures/open-design/erp-records.json`` produce the committed
``expected.json``; the TypeScript suite parses it and expands the runs. Regenerate after a deliberate
change with ``python3 -B tests/portal_unit/test_system_design_expansion.py --write``.
"""

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from test_services import ROOT, Record, load_service

EXPANSION = ROOT + ".system_design.expansion"
GATE = ROOT + ".system_design.gate"
FIXTURES = (
	Path(__file__).resolve().parents[2] / "tools/system_designer/packages/core-schemas/fixtures/open-design"
)
RECORDS = json.loads((FIXTURES / "erp-records.json").read_text(encoding="utf-8"))


def expected_payload(module, records):
	context = records["context"]
	lines = [
		module.serialize_line(line, idx, context["engine"]) for idx, line in enumerate(records["lines"], 1)
	]
	builds = {}
	for doc in records["docs"]:
		builds.setdefault(doc["doctype"], {})[doc["name"]] = module.BUILDERS[doc["doctype"]](doc, context)
	return {
		"lines": lines,
		"builds": builds,
		"readiness": module.readiness_summary(lines, builds, records["catalog_kinds"]),
	}


class Expansion(unittest.TestCase):
	def setUp(self):
		self.context = load_service(EXPANSION)
		self.module, _frappe = self.context.__enter__()
		self.payload = expected_payload(self.module, copy.deepcopy(RECORDS))
		self.lines = {line["lineId"]: line for line in self.payload["lines"]}
		self.builds = {
			name: build for group in self.payload["builds"].values() for name, build in group.items()
		}

	def tearDown(self):
		self.context.__exit__(None, None, None)

	def test_committed_payload_matches(self):
		expected = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
		self.assertEqual(json.loads(json.dumps(self.payload)), expected)

	def test_line_kinds_and_keys(self):
		kinds = {line_id: line["kind"] for line_id, line in self.lines.items()}
		self.assertEqual(
			kinds,
			{
				"A1": "configured",
				"B1": "configured",
				"C1": "configured",
				"D1": "configured",
				"E1": "third-party",
				"F1": "third-party",
				"G1": "configured",
				"H1": "accessory",
				"I1": "unconfigured",
				"WIRE1": "writeback",
			},
		)
		self.assertEqual(self.lines["G1"]["key"], "G1-7")
		self.assertIsNone(self.lines["G1"]["lineKey"])
		self.assertEqual(self.lines["D1"]["configured"]["doctype"], "ilL-Configured-Group")
		third = self.lines["E1"]["thirdParty"]
		self.assertEqual(
			(third["wattsEach"], third["dimming"], third["voltageClass"]),
			(12, "phase-forward", "Line Voltage"),
		)

	def test_linear_runs_in_order_with_tape_catalog_id(self):
		build = self.builds["ILL-CF-LINEAR"]
		self.assertEqual([run["runIndex"] for run in build["runs"]], [1, 2])
		self.assertEqual(build["runs"][0], {"runIndex": 1, "lengthFt": 6, "watts": 26.4, "feedMethod": "end"})
		self.assertEqual(build["catalogId"], "tape:TEST-TAPE-24:4.4:50")
		self.assertEqual(build["environment"], "dry-concealed")
		self.assertEqual(
			build["allocations"][1], {"runKey": "2", "supply": 1, "output": 2, "itemCode": "TEST-PSU-96"}
		)
		wet = self.builds["ILL-CF-WET"]
		self.assertEqual((wet["environment"], wet["runs"][0]["feedMethod"]), ("wet", "center"))
		self.assertEqual(wet["catalogId"], "tape:TEST-TAPE-24:6.2:100")

	def test_jumpered_tape_runs_are_connected(self):
		build = self.builds["ILL-CTN-00001"]
		self.assertEqual(
			[(run["runIndex"], run["lengthFt"], run["watts"]) for run in build["runs"]],
			[(1, 4.9213, 21.6), (2, 9.8425, 43.3)],
		)
		self.assertEqual(build["protocols"], ["DMX512"])
		self.assertEqual(build["maxRunFtEffective"], 16)

	def test_jumper_over_the_limit_is_an_issue(self):
		records = copy.deepcopy(RECORDS)
		tape = next(doc for doc in records["docs"] if doc["name"] == "ILL-CTN-00001")
		snapshot = json.loads(tape["build_snapshot_json"])
		snapshot["computed"]["max_run_ft_effective"] = 4
		tape["build_snapshot_json"] = json.dumps(snapshot)
		build = self.module.tape_neon_build(tape, records["context"])
		self.assertIn("exceeds the approved run limit", build["issues"][0])

	def test_sheet_and_group(self):
		sheet = self.builds["ILL-CLS-00001"]
		self.assertEqual(
			[(r["runIndex"], r["lengthFt"], r["watts"]) for r in sheet["runs"]],
			[(1, None, 50), (2, None, 40)],
		)
		self.assertEqual(sheet["catalogId"], "sheet:TEST-SHEET")
		group = self.builds["ILL-CG-00001"]
		self.assertEqual(
			[(r["runIndex"], r["lengthFt"], r["watts"]) for r in group["runs"]], [(1, 3, 13.2), (2, 6, 26.4)]
		)
		self.assertEqual([a["runKey"] for a in group["allocations"]], ["1", "2"])
		self.assertIsNone(group["environment"])
		self.assertEqual(group["catalogId"], "tape:TEST-TAPE-24:4.4:50")

	def test_readiness(self):
		readiness = self.payload["readiness"]
		self.assertEqual(readiness["ready"], ["a1linear", "b1tape", "d1group", "e1other", "G1-7"])
		self.assertEqual(
			readiness["needs_data"], [{"key": "f1other", "reason": "Enter the watts for this fixture"}]
		)
		self.assertEqual(readiness["unconfigured"], ["i1new"])
		self.assertEqual(
			readiness["catalog_gaps"],
			[
				{
					"key": "c1sheet",
					"catalogId": "sheet:TEST-SHEET",
					"reason": "This product is not in the design catalog yet",
				}
			],
		)
		self.assertEqual(readiness["missing_line_keys"], ["G1-7"])

	def test_environment_rules(self):
		env = self.module.environment_for
		self.assertEqual(env("Indoor"), "dry-concealed")
		self.assertEqual(env("Outdoor Wet"), "outdoor-exposed")
		self.assertEqual(env("X", {"X": ("Direct Burial", "DB")}), "direct-burial")
		self.assertIsNone(env("Mystery"))
		self.assertIsNone(env(None))


class Gate(unittest.TestCase):
	def values(self, **changes):
		values = {"review_gate_enabled": 1, "review_gate_watts": 1500, "review_gate_dmx": 1}
		return Record(**{**values, "review_gate_phase_dimming": 1, **changes})

	def test_off_unless_settings_and_site_flag(self):
		with load_service(GATE) as (module, _frappe), load_service(EXPANSION) as (expansion, _f):
			payload = expected_payload(expansion, copy.deepcopy(RECORDS))
			with patch.object(module, "gate_enabled", return_value=False):
				result = module.review_requirement(payload["lines"], payload["builds"], self.values())
			self.assertEqual(
				result, {"required": False, "reasons": [], "satisfied": True, "approved_design": None}
			)
			with patch.object(module, "gate_enabled", return_value=True):
				result = module.review_requirement(payload["lines"], payload["builds"], self.values())
			self.assertEqual([r["code"] for r in result["reasons"]], ["DMX", "PHASE_DIMMING"])
			self.assertFalse(result["satisfied"])
			reasons = module.reasons_for(
				payload["lines"], payload["builds"], self.values(review_gate_watts=100)
			)
			self.assertEqual(reasons[0]["code"], "LOAD_OVER_THRESHOLD")
			self.assertEqual(reasons[0]["detail"], "403 W")


def write_expected():
	with load_service(EXPANSION) as (module, _frappe):
		payload = expected_payload(module, copy.deepcopy(RECORDS))
		(FIXTURES / "expected.json").write_text(
			json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
		)


if __name__ == "__main__":
	if "--write" in sys.argv:
		write_expected()
	else:
		unittest.main()
