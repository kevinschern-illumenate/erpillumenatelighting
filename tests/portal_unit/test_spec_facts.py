"""Shared spec facts: one formatter per value for Webflow, the CSV export and spec sheets."""

import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.spec_sheets import facts

APP = Path(__file__).resolve().parents[2] / "illumenate_lighting" / "illumenate_lighting"
CALLERS = (
	APP / "api" / "spec_sheet_export.py",
	APP / "api" / "webflow_export.py",
	APP / "doctype" / "ill_webflow_product" / "ill_webflow_product.py",
)


class Formatters(unittest.TestCase):
	"""Outputs the three former copies produced; changing one changes the website and the CSV."""

	def test_temperature_and_beam_angle(self):
		self.assertEqual(facts.operating_temperature(-40, 65), "-40°F (-40°C) to 149°F (65°C)")
		self.assertEqual(facts.operating_temperature(-20.0, 45.0), "-4°F (-20.0°C) to 113°F (45.0°C)")
		self.assertEqual(facts.operating_temperature(None, 45), "")
		self.assertEqual(facts.operating_temperature(0, 0), "32°F (0°C) to 32°F (0°C)")
		self.assertEqual(
			(facts.beam_angle(120), facts.beam_angle(37.5), facts.beam_angle(0)), ("120°", "37.5°", "")
		)

	def test_voltages(self):
		self.assertEqual(
			[facts.voltage_value(value, "VDC") for value in ("24", "24V", "24 v", "24VDC", 12, "", None)],
			["24VDC", "24VDC", "24 vDC", "24VDC", "12VDC", "", ""],
		)
		self.assertEqual(facts.output_voltage("24", "120"), "24VDC")
		self.assertEqual(facts.output_voltage(None, "120"), "120VAC")
		self.assertEqual(facts.output_voltage(None, None, "24V DC"), "24V DC")
		self.assertEqual(facts.driver_input_voltage(120, 277, None), "120V-277VAC")
		self.assertEqual(facts.driver_input_voltage(120, None, "VAC"), "")
		self.assertEqual(facts.input_voltage("24VDC", "120V-277VAC"), "24VDC (Power Supply: 120V-277VAC)")
		self.assertEqual(
			(facts.input_voltage("24VDC", ""), facts.input_voltage("", "120V-277VAC")),
			("24VDC", "120V-277VAC"),
		)

	def test_lengths_power_and_quality(self):
		self.assertEqual(facts.mm_interval(50), '1.97" (50mm)')
		self.assertEqual(facts.mm_interval(62.5), '2.46" (62.5mm)')
		self.assertEqual(facts.mm_interval(25.4), '1" (25.4mm)')
		self.assertEqual([facts.mm_interval(value) for value in (None, "", 0, "abc")], ["", "", "", ""])
		self.assertEqual(facts.production_interval(50, free_cutting=True), "Free-Cutting")
		self.assertEqual(facts.max_footage_per_100w_supply(4.4), 18.2)
		self.assertEqual(facts.format_max_footage_per_100w_supply(2), "40ft")
		self.assertEqual(facts.format_max_footage_per_100w_supply(0), "")
		self.assertEqual(facts.cri_quality("95 CRI", 2), "95 CRI / 2 SDCM")
		self.assertEqual((facts.cri_quality(None, 3), facts.cri_quality("90 CRI", "")), ("3 SDCM", "90 CRI"))

	def test_callers_do_not_carry_their_own_copies(self):
		for path in CALLERS:
			source = path.read_text(encoding="utf-8")
			with self.subTest(path=path.name):
				self.assertIn("facts.operating_temperature(", source)
				self.assertNotIn("9 / 5 + 32", source)
				# Dimming comes from driver_catalog.approved_input_protocols everywhere.
				self.assertNotIn(
					'filters={"fixture_template": self.fixture_template, "is_active": 1}', source
				)
				self.assertNotIn(
					'filters={"fixture_template": product["fixture_template"], "is_active": 1}', source
				)
				self.assertNotIn("(Power Supply: {", source)


class DimmingUnion(unittest.TestCase):
	def test_every_approved_enabled_driver_contributes_in_priority_order(self):
		drivers = {
			"DRV-A": Record(
				item="ITEM-A", input_protocols=[Record(protocol="0-10V"), Record(protocol="TRIAC")]
			),
			"DRV-B": Record(
				item="ITEM-B", input_protocols=[Record(protocol="DALI"), Record(protocol="0-10V")]
			),
			"DRV-OFF": Record(item="ITEM-OFF", input_protocols=[Record(protocol="DMX")]),
		}
		with load_service(ROOT + ".api.driver_catalog") as (module, frappe):
			frappe.get_all.return_value = [Record(driver_spec=name) for name in ("DRV-A", "DRV-B", "DRV-OFF")]
			frappe.get_doc.side_effect = lambda doctype, name: types.SimpleNamespace(**drivers[name])
			frappe.db.get_value.side_effect = lambda doctype, name, field: name == "ITEM-OFF"
			self.assertEqual(
				module.approved_input_protocols("ilL-Fixture-Template", "SH01"), ["0-10V", "TRIAC", "DALI"]
			)
			filters = frappe.get_all.call_args.kwargs["filters"]
			self.assertEqual((filters["is_allowed"], filters["is_active"]), (1, 1))
			self.assertEqual(filters["template_type"], "ilL-Fixture-Template")
			self.assertTrue(frappe.get_all.call_args.kwargs["order_by"].startswith("priority asc"))


class CsvExportDrivers(unittest.TestCase):
	def test_csv_prints_the_preferred_supply_and_the_full_dimming_union(self):
		stubs = {
			"frappe.utils": types.SimpleNamespace(get_url=lambda *args: ""),
			"frappe.utils.file_manager": types.SimpleNamespace(save_file=MagicMock()),
			ROOT + ".doctype.ill_spec_profile.ill_spec_profile": types.SimpleNamespace(
				compute_profile_dimensions=MagicMock()
			),
			ROOT + ".api.driver_catalog": types.SimpleNamespace(
				approved_input_protocols=lambda template_type, template: ["TRIAC", "DALI", "0-10V"]
			),
		}
		with load_service(ROOT + ".api.spec_sheet_export", stubs) as (module, frappe):
			frappe.get_all.return_value = [Record(driver_spec="DRV-A")]
			frappe.get_cached_doc = lambda doctype, name: types.SimpleNamespace(
				input_voltage_min=120, input_voltage_max=277, input_voltage_type="VAC", max_wattage=96
			)
			info = module._get_preferred_driver_info("ilL-Fixture-Template", "SH01")
		self.assertEqual(info["input_voltage"], "120V-277VAC")
		self.assertEqual(info["max_wattage"], 96)
		self.assertEqual(sorted(info["dimming_protocols"]), ["0-10V", "DALI", "TRIAC"])


if __name__ == "__main__":
	unittest.main()
