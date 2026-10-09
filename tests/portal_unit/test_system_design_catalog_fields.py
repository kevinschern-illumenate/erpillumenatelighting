"""System Designer catalog fields (WP-1.1): voltage parsing, protocol mapping, the pre-fill patch."""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

REPO = Path(__file__).resolve().parents[2]
TABLE = REPO / "tools/system_designer/packages/data/src/protocols.json"


class Units(unittest.TestCase):
	def test_parse_voltage_takes_the_first_label_with_volts(self):
		with load_service(ROOT + ".system_design.units") as (units, _frappe):
			self.assertEqual(units.parse_voltage("24V"), 24.0)
			self.assertEqual(units.parse_voltage(None, "", "12 VDC"), 12.0)
			self.assertEqual(units.parse_voltage("Low voltage 5.5v"), 5.5)
			self.assertIsNone(units.parse_voltage("", None, "Universal"))

	def test_conversions_round_to_four_places(self):
		with load_service(ROOT + ".system_design.units") as (units, _frappe):
			self.assertEqual(units.mm_to_in(50), 1.9685)
			self.assertEqual(units.mm_to_ft(304.8), 1.0)
			self.assertEqual(units.m_to_ft(5), 16.4042)
			self.assertEqual(units.per_m_to_per_ft(60), 18.2880)


class Protocols(unittest.TestCase):
	def test_python_and_typescript_tables_are_identical(self):
		with load_service(ROOT + ".system_design.protocols") as (protocols, _frappe):
			table = json.loads(TABLE.read_text(encoding="utf-8"))
			self.assertEqual(list(protocols.ENGINE_PROTOCOLS), table["engineProtocols"])
			self.assertEqual(protocols.ATTRIBUTE_PROTOCOLS, table["attributeProtocols"])
			self.assertEqual(sorted(protocols.PHASE_PROTOCOLS), table["phaseProtocols"])
			self.assertEqual(sorted(protocols.DMX_PROTOCOLS), table["dmxProtocols"])

	def test_attribute_choice_wins_then_label_rules(self):
		with load_service(ROOT + ".system_design.protocols") as (protocols, _frappe):
			cases = {
				("TRIAC", "anything"): "phase-forward",
				("ELV", None): "phase-reverse",
				("DMX/RDM", None): "DMX512",
				(None, "Lutron EcoSystem"): "Lutron-EcoSystem",
				(None, "Lutron QS"): "Lutron-QS",
				(None, "0-10V Dimming"): "0-10V",
				(None, "1-10 V"): "1-10V",
				(None, "DALI-2 DT8"): "DALI-2",
				(None, "Reverse-phase (ELV)"): "phase-reverse",
				(None, "Forward phase"): "phase-forward",
				(None, "Non-dimming"): "none",
				(None, "Casambi Bluetooth"): None,
			}
			for (choice, label), expected in cases.items():
				with self.subTest(choice=choice, label=label):
					self.assertEqual(protocols.engine_protocol_for(choice, label), expected)
			for value in protocols.ATTRIBUTE_PROTOCOLS.values():
				self.assertIn(value, protocols.ENGINE_PROTOCOLS)


class PrefillPatch(unittest.TestCase):
	def run_patch(self, rows):
		with load_service("illumenate_lighting.patches.system_designer_tape_fields") as (patch, frappe):
			frappe.db.has_column.return_value = True
			frappe.get_all.side_effect = lambda doctype, fields=None, **kw: [
				Record(r) for r in rows.get(doctype, [])
			]
			frappe.db.set_value = MagicMock()
			patch.execute()
			return frappe.db.set_value.call_args_list

	def test_fills_only_empty_values(self):
		calls = self.run_patch(
			{
				"ilL-Attribute-Output Voltage": [
					{"name": "24VDC", "dc_voltage": "24V", "nominal_voltage_v": 0},
					{"name": "12V", "dc_voltage": "", "voltage_name": "12V", "nominal_voltage_v": 12},
					{"name": "Universal", "voltage_name": "Universal", "nominal_voltage_v": None},
				],
				"ilL-Attribute-Dimming Protocol": [
					{"name": "TRIAC", "protocol": "TRIAC", "label": "TRIAC", "engine_protocol": ""},
					{"name": "DALI", "protocol": "DALI", "label": "DALI", "engine_protocol": "DALI-2"},
					{"name": "Casambi", "protocol": "", "label": "Casambi", "engine_protocol": None},
				],
				"ilL-Attribute-LED Package": [
					{"name": "RGBW", "channels": 0, "spectrum_type": "RGBW"},
					{"name": "TW", "channels": 2, "spectrum_type": "Tunable White"},
					{"name": "DTW", "channels": 0, "spectrum_type": "Dim to Warm"},
				],
				"ilL-Spec-LED Tape": [
					{
						"name": "T1",
						"led_package": "RGBW",
						"voltage_drop_max_run_length_ft": 16,
						"channels": 1,
					},
					{
						"name": "T2",
						"led_package": "TW",
						"max_run_single_feed_ft": 20,
						"channels": 1,
						"max_simultaneous_pct": 150,
					},
					{"name": "T3", "led_package": "DTW", "channels": 1},
					{
						"name": "T4",
						"led_package": "TW",
						"max_run_single_feed_ft": 20,
						"channels": 2,
						"max_simultaneous_pct": 200,
					},
				],
			}
		)
		writes = [(c.args[0], c.args[1], *c.args[2:]) for c in calls]
		self.assertIn(("ilL-Attribute-Output Voltage", "24VDC", "nominal_voltage_v", 24.0), writes)
		self.assertIn(("ilL-Attribute-Dimming Protocol", "TRIAC", "engine_protocol", "phase-forward"), writes)
		self.assertIn(
			(
				"ilL-Spec-LED Tape",
				"T1",
				{"max_run_single_feed_ft": 16, "channels": 4, "max_simultaneous_pct": 400},
			),
			writes,
		)
		self.assertIn(("ilL-Spec-LED Tape", "T2", {"channels": 2}), writes)
		self.assertIn(("ilL-Spec-LED Tape", "T3", {"max_simultaneous_pct": 100}), writes)
		touched = {(w[0], w[1]) for w in writes}
		for untouched in (
			("ilL-Attribute-Output Voltage", "12V"),
			("ilL-Attribute-Output Voltage", "Universal"),
			("ilL-Attribute-Dimming Protocol", "DALI"),
			("ilL-Attribute-Dimming Protocol", "Casambi"),
			("ilL-Spec-LED Tape", "T4"),
		):
			self.assertNotIn(untouched, touched)
		for call in calls:
			self.assertEqual(call.kwargs, {"update_modified": False})

	def test_skips_cleanly_before_the_columns_exist(self):
		with load_service("illumenate_lighting.patches.system_designer_tape_fields") as (patch, frappe):
			frappe.db.has_column.return_value = False
			frappe.db.set_value = MagicMock()
			patch.execute()
			frappe.get_all.assert_not_called()
			frappe.db.set_value.assert_not_called()


if __name__ == "__main__":
	unittest.main()
