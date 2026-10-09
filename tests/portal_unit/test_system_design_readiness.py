"""Design readiness rule table (System Designer H7.2, WP-1.7)."""

import unittest
from unittest.mock import MagicMock

from test_services import ROOT, load_service

READINESS = ROOT + ".system_design.readiness"
VOLTS = {"24VDC": 24, "120VAC": 120, "Blank": None}
ENGINE = {"0-10V": "0-10V", "DMX": "DMX512", "Mystery": None}

TAPE = {
	"item": "TAPE-1",
	"input_voltage": "24VDC",
	"drive_type": "CV",
	"power_basis": "All Channel Max",
	"watts_per_foot": 4.4,
	"max_simultaneous_pct": 100,
	"voltage_drop_max_run_length_ft": 16,
	"max_run_double_feed_ft": 32,
	"min_operating_voltage_v": 20,
	"channels": 1,
	"is_free_cutting": 0,
	"cut_increment_mm": 50,
	"pixel_protocol": "None",
}
DRIVER = {
	"item": "PSU-96",
	"input_voltage_type": "VAC",
	"input_voltage_min": 100,
	"input_voltage_max": 277,
	"input_phase": "1PH",
	"output_type": "Constant Voltage",
	"voltage_output": "24VDC",
	"max_wattage": 96,
	"max_wattage_per_output": 96,
	"independent_outputs_count": 1,
	"efficiency": 0.9,
	"power_factor": 0.95,
	"usable_load_factor": 0.8,
	"terminal_min_awg": "18",
	"terminal_max_awg": "12",
}
DECODER = {
	"item": "DEC-4",
	"controller_type": "DMX Decoder",
	"input_voltage_type": "VDC",
	"channels": 4,
	"max_a_per_channel": 5,
	"max_load_amps": 20,
	"max_w_per_channel": 120,
	"max_load_watts": 480,
	"dmx_footprint": 4,
	"unit_load": 1,
}


class Rules(unittest.TestCase):
	def setUp(self):
		self.context = load_service(READINESS)
		self.module, _frappe = self.context.__enter__()

	def tearDown(self):
		self.context.__exit__(None, None, None)

	def tape(self, **changes):
		return self.module.tape_issues({**TAPE, **changes}, VOLTS)

	def driver(self, protocols=("0-10V",), **changes):
		return self.module.driver_issues({**DRIVER, **changes}, VOLTS, ENGINE, list(protocols))

	def controller(self, inputs=("DMX",), outputs=(), ports=1, **changes):
		return self.module.controller_issues(
			{**DECODER, **changes}, ENGINE, list(inputs), list(outputs), ports
		)

	def test_complete_records_are_ready(self):
		for result in (self.tape(), self.driver(), self.controller()):
			self.assertEqual((result["status"], result["missing"]), ("ready", []))

	def test_tape_voltage_must_be_12_24_or_48(self):
		result = self.tape(input_voltage="120VAC")
		self.assertEqual(result["missing"], ["input_voltage"])
		self.assertIn("120 V", result["notes"][0])
		self.assertEqual(self.tape(input_voltage="Blank")["missing"], ["input_voltage"])
		self.assertEqual(self.tape(input_voltage=None)["missing"], ["input_voltage"])

	def test_tape_required_fields_use_erp_names(self):
		result = self.tape(
			drive_type=None, watts_per_foot=0, voltage_drop_max_run_length_ft=None, cut_increment_mm=None
		)
		self.assertEqual(result["status"], "incomplete")
		self.assertEqual(
			result["missing"], ["drive_type", "watts_per_foot", "max_run_single_feed_ft", "cut_increment_mm"]
		)
		self.assertEqual(self.tape(is_free_cutting=1, cut_increment_mm=None)["missing"], [])
		self.assertEqual(
			self.tape(max_run_single_feed_ft=20, voltage_drop_max_run_length_ft=None)["missing"], []
		)

	def test_pixel_tape_needs_pixel_data(self):
		self.assertEqual(
			self.tape(pixel_protocol="WS2811")["missing"], ["pixels_per_m", "amps_per_pixel_max"]
		)

	def test_multichannel_tape_without_limits_is_a_note(self):
		result = self.tape(channels=3, channel_limit_count=0)
		self.assertEqual(result["status"], "ready")
		self.assertIn("CH1 to CH3", result["notes"][0])

	def test_driver_output_rules(self):
		self.assertEqual(self.driver(voltage_output="Blank")["missing"], ["voltage_output"])
		result = self.driver(output_type="Constant Current", voltage_output=None)
		self.assertEqual(result["missing"], ["output_current_ma", "compliance_v_min", "compliance_v_max"])
		result = self.driver(efficiency=90)
		self.assertEqual(result["missing"], ["efficiency"])
		self.assertIn("between 0 and 1", result["notes"][0])

	def test_unmapped_or_missing_protocols(self):
		result = self.driver(protocols=("Mystery",))
		self.assertEqual(result["missing"], ["input_protocols"])
		self.assertEqual(result["notes"], ["unmapped protocol: Mystery"])
		self.assertEqual(self.driver(protocols=())["missing"], ["input_protocols"])
		self.assertEqual(self.controller(inputs=(), outputs=())["missing"], ["input_protocols"])
		self.assertEqual(self.controller(outputs=("Mystery",))["missing"], ["output_protocols"])

	def test_decoder_rules(self):
		result = self.controller(max_load_watts=None, dmx_footprint=0, ports=0)
		self.assertEqual(result["missing"], ["max_load_watts", "dmx_footprint", "ports"])
		self.assertEqual(self.controller(input_voltage_type="VAC")["missing"], ["output_dimming"])
		self.assertEqual(
			self.controller(input_voltage_type="VAC", output_dimming="Phase Forward")["missing"], []
		)

	def test_controller_categories(self):
		category = self.module.controller_category
		self.assertEqual(category("Wall Dimmer", "Phase Reverse"), "phase-dimmer")
		self.assertEqual(category("Wall Dimmer", "0-10V"), "0-10v-dimmer")
		self.assertIsNone(category("Wall Dimmer", "None"))
		self.assertEqual(category("Gateway"), "sacn-gateway")
		dimmer = {"item": "DIM", "controller_type": "Wall Dimmer", "output_dimming": "Phase Forward"}
		result = self.module.controller_issues(dimmer, ENGINE, ["0-10V"], [], 1)
		self.assertEqual(result["missing"], ["min_load_w", "led_max_w", "max_supplies"])
		result = self.module.controller_issues({**dimmer, "output_dimming": None}, ENGINE, ["0-10V"], [], 1)
		self.assertEqual(result["missing"], ["output_dimming"])
		sensor = self.module.controller_issues({"item": "S", "controller_type": "Sensor"}, ENGINE, [], [], 0)
		self.assertEqual((sensor["status"], sensor["missing"]), ("not modelled", []))

	def test_wire_needs_a_selling_price(self):
		result = self.module.wire_issues({"item": "W1", "is_verified": 1}, has_price=False)
		self.assertEqual(result["missing"], ["item_price"])
		self.assertEqual(self.module.wire_issues({"item": "W1", "is_verified": 1}, True)["missing"], [])
		self.assertIn("Not verified", self.module.wire_issues({"item": "W1"}, True)["notes"][0])

	def test_volume_and_ordering(self):
		rows = [
			{"product_type": "Tape", "name": "T1", "item": "T1", "status": "ready"},
			{"product_type": "Driver", "name": "D1", "item": "D1", "status": "incomplete"},
			{"product_type": "Wire", "name": "W1", "item": "W1", "status": "incomplete"},
		]
		ordered = self.module.with_volume(rows, {"tape": {"T1": 9}, "item": {"D1": 2, "W1": 5, "T1": 99}})
		self.assertEqual([(r["name"], r["volume"]) for r in ordered], [("W1", 5), ("D1", 2), ("T1", 9)])
		summary = self.module.summarize(ordered)
		self.assertEqual((summary["total"], summary["incomplete"]), (3, 2))
		self.assertEqual(summary["by_type"]["Wire"], {"total": 1, "incomplete": 1})


class Access(unittest.TestCase):
	def test_report_needs_catalog_engineering_or_review(self):
		staff = MagicMock()
		staff.allowed.return_value = False
		with load_service(READINESS, {ROOT + ".portal.staff": staff}) as (module, _frappe):
			with self.assertRaises(PermissionError):
				module.get_report()


if __name__ == "__main__":
	unittest.main()
