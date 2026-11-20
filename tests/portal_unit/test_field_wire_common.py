"""PRD question 6: the commonly stocked field wire import file is complete and importable."""

import sys
import types
import unittest
from pathlib import Path

from test_services import ROOT, load_service

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.seed_imports import field_wire_common


class FieldWireCommon(unittest.TestCase):
	def setUp(self):
		extras = {
			ROOT + ".system_design.api": types.SimpleNamespace(endpoint=lambda function: function),
			ROOT + ".system_design.access": types.SimpleNamespace(require_capability=lambda name: None),
		}
		self.context = load_service(ROOT + ".system_design.wire_import", extras)
		self.module, _frappe = self.context.__enter__()

	def tearDown(self):
		self.context.__exit__(None, None, None)

	def test_committed_csv_matches_the_generator(self):
		self.assertEqual(field_wire_common.TARGET.read_text(encoding="utf-8"), field_wire_common.csv_text())

	def test_every_row_parses_without_problems(self):
		rows = self.module.parse_csv(field_wire_common.TARGET.read_text(encoding="utf-8"))
		self.assertEqual(len(rows), len(field_wire_common.ROWS))
		for row in rows:
			with self.subTest(row["item_code"]):
				self.assertEqual(row["problems"], [])
				self.assertTrue(row["item_code"].startswith("FW-"))
				self.assertEqual(row["spec"]["is_verified"], 0)
				self.assertIn("http", row["spec"]["source_reference"])

	def test_every_spec_is_ready_except_its_price(self):
		with load_service(ROOT + ".system_design.readiness") as (readiness, _frappe):
			for row in self.module.parse_csv(field_wire_common.TARGET.read_text(encoding="utf-8")):
				with self.subTest(row["item_code"]):
					result = readiness.wire_issues({**row["spec"], "item": row["item_code"]}, False, row["spec"]["conductors"])
					self.assertEqual(result["missing"], ["item_price"])

	def test_covers_every_cable_run_type_the_designer_selects(self):
		applications = set()
		for row in field_wire_common.ROWS:
			applications |= set(row["applications"].split(","))
		for run_type in ("class2-dc", "class2-dc-multichannel", "landscape-ac", "lv-branch", "dmx", "ethernet", "spi-data", "0-10v", "dali", "lutron-qs"):
			self.assertIn(run_type, applications)


if __name__ == "__main__":
	unittest.main()
