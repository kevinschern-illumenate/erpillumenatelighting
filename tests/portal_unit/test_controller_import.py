"""Controls in v1 (PRD question 7): the Desk controller import and the common controls file."""

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, load_service

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.seed_imports import controls_common

EXTRAS = {
	ROOT + ".system_design.api": types.SimpleNamespace(endpoint=lambda function: function),
	ROOT + ".system_design.access": types.SimpleNamespace(require_capability=lambda name: None),
}
HEADER = ",".join(controls_common.COLUMNS)


class ControllerImport(unittest.TestCase):
	def setUp(self):
		self.context = load_service(ROOT + ".system_design.controller_import", EXTRAS)
		self.module, self.frappe = self.context.__enter__()
		self.existing = {"ilL-Attribute-Dimming Protocol": {"DMX512", "SPI", "PWM"}, "Item Group": {"All Item Groups"}}
		self.frappe.db.exists.side_effect = lambda doctype, name=None: (
			name in self.existing.get(doctype, set()) if isinstance(name, str) else False
		)
		self.inserted = []

		def get_doc(values):
			doc = MagicMock()
			doc.values = values
			doc.insert.side_effect = lambda **kwargs: self.inserted.append(values)
			doc.append.side_effect = lambda table, row: values.setdefault(table, []).append(row)
			return doc

		self.frappe.get_doc.side_effect = get_doc

	def tearDown(self):
		self.context.__exit__(None, None, None)

	def test_committed_csv_matches_the_generator(self):
		self.assertEqual(controls_common.TARGET.read_text(encoding="utf-8"), controls_common.csv_text())

	def test_common_controls_parse_without_problems(self):
		rows = self.module.plan_rows(self.module.parse_csv(controls_common.TARGET.read_text(encoding="utf-8")))
		self.assertEqual(len(rows), len(controls_common.ROWS))
		for row in rows:
			with self.subTest(row["item_code"]):
				self.assertEqual(row["problems"], [])
				self.assertIn("http", row["spec"]["notes"])
		pixel = next(row for row in rows if row["item_code"] == "ADVATEK-A4-S-MK3")
		self.assertEqual([port["port_name"] for port in pixel["ports"]], ["OUT1", "OUT2", "OUT3", "OUT4", "Ethernet"])
		self.assertEqual(pixel["ports"][0], {"port_name": "OUT1", "direction": "Out", "protocol": "SPI", "max_devices": 1020})
		self.assertEqual(pixel["spec"]["max_pixels"], 4080)

	def test_readiness_flags_only_what_the_sheets_do_not_give(self):
		rows = self.module.parse_csv(controls_common.TARGET.read_text(encoding="utf-8"))
		engine = {"DMX512": "DMX512", "SPI": "SPI", "sACN": "sACN", "Art-Net": "Art-Net"}
		with load_service(ROOT + ".system_design.readiness") as (readiness, _frappe):
			for row in rows:
				with self.subTest(row["item_code"]):
					result = readiness.controller_issues(
						row["spec"], engine, row["protocols"]["input_protocols"], row["protocols"]["output_protocols"], row["ports"]
					)
					expected = {"terminal_max_awg"} | ({"input_voltage_min", "input_voltage_max"} if row["item_code"] == "ADVATEK-PIXLITE-16-MK2" else set())
					self.assertEqual(set(result["missing"]), expected)

	def test_bad_rows_are_reported(self):
		text = "\n".join(
			[
				HEADER,
				"X1,,X one,Laser Controller,VXX,,,-1,1.5,,,,,,,,,,Dim,99,,,,DMX 1:Sideways:DMX512; A:Out,,src,1",
				"X1,,X two,Pixel Controller,VDC,,,,,,,,,,,,,,None,,,Mystery,,OUT1:In:SPI:10,,src,1",
			]
		) + "\n"
		rows = self.module.plan_rows(self.module.parse_csv(text))
		first = " | ".join(rows[0]["problems"])
		for fragment in ("Unknown controller type", "VAC or VDC", "cannot be negative", "whole number", "output_dimming", "AWG", "direction", "should look like"):
			self.assertIn(fragment, first)
		second = " | ".join(rows[1]["problems"])
		self.assertIn("repeated", second)
		self.assertIn("device limits apply to output ports", second)
		self.assertIn("Protocol 'Mystery'", second)

	def test_import_creates_missing_ethernet_protocols_items_and_specs(self):
		report = self.module.import_controller_csv(controls_common.TARGET.read_text(encoding="utf-8"), dry_run=False)
		self.assertTrue(report["written"], report)
		protocols = [doc for doc in self.inserted if doc["doctype"] == "ilL-Attribute-Dimming Protocol"]
		self.assertEqual({doc["label"]: doc["engine_protocol"] for doc in protocols}, {"sACN": "sACN", "Art-Net": "Art-Net"})
		specs = [doc for doc in self.inserted if doc["doctype"] == "ilL-Spec-Controller"]
		self.assertEqual(len(specs), 5)
		lpc = next(doc for doc in specs if doc["item"] == "PHAROS-LPC-1")
		self.assertEqual([row["protocol"] for row in lpc["output_protocols"]], ["DMX512"])
		self.assertEqual(len(lpc["ports"]), 3)
		self.assertTrue(any(doc["doctype"] == "Item Group" and doc["item_group_name"] == "Lighting Controls" for doc in self.inserted))

	def test_dry_run_writes_nothing(self):
		report = self.module.import_controller_csv(controls_common.TARGET.read_text(encoding="utf-8"))
		self.assertFalse(report["written"])
		self.assertEqual(self.inserted, [])


if __name__ == "__main__":
	unittest.main()
