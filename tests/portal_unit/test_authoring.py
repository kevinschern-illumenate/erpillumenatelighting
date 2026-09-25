"""Engineering readiness is the same data contract for Desk and generated imports."""

import csv
import tempfile
import unittest
from pathlib import Path

from illumenate_lighting.illumenate_lighting.api.authoring_contract import record_issues
from tools.fixture_builder.config_schema import (
	DriverDef,
	FixtureBuilderConfig,
	LedSheetSpecDef,
	LedSheetTemplateDef,
)
from tools.fixture_builder.generators import gen_led_sheet_template, gen_rel_driver_eligibility


class Authoring(unittest.TestCase):
	def test_csv_unknown_fields_and_nonfinite_wattage_fail_preflight(self):
		from tools.validate_authoring_csv import validate

		with tempfile.TemporaryDirectory() as directory:
			path = Path(directory) / "ilL-Spec-LED-Sheet.csv"
			path.write_text(
				"Item,Unknown Electrical Guess,Total Sheet Watts\nPANEL,20,nan\n", encoding="utf-8"
			)
			result = validate(path)
			self.assertFalse(result["valid"])
			self.assertTrue(any(issue["field"] == "Unknown Electrical Guess" for issue in result["issues"]))
			self.assertTrue(any(issue["field"] == "total_sheet_watts" for issue in result["issues"]))

	def test_pdf_generator_exports_required_core_values_and_actual_sheet_jumpers(self):
		from tools.fixture_builder.generators import gen_led_sheet_submittal_mapping

		config = FixtureBuilderConfig(
			product_type="led-sheet", led_sheet_templates=[LedSheetTemplateDef(template_code="Snowfield")]
		)
		with tempfile.TemporaryDirectory() as directory:
			path = gen_led_sheet_submittal_mapping.generate(config, directory)
			with Path(path).open(encoding="utf-8", newline="") as stream:
				rows = {row["PDF Field Name"]: row for row in csv.DictReader(stream)}
			self.assertEqual(rows["jumper_cables_extra"]["Source Field"], "jumper_cables_included")
			self.assertEqual(rows["total_system_watts"]["Required Value"], "1")
			self.assertEqual(rows["project_name"]["Required Value"], "0")

	def test_driver_color_channels_are_not_assumed_independent(self):
		driver = dict(
			item="PS",
			voltage_output="24V",
			output_type="Constant Voltage",
			output_protocol="PWM",
			outputs_count=2,
			max_wattage=100,
			max_wattage_per_output=60,
			usable_load_factor=0.8,
			input_protocols=[{"protocol": "0-10V"}],
		)
		self.assertIn(
			"independent_outputs_count", {row["field"] for row in record_issues("ilL-Spec-Driver", driver)}
		)
		driver["independent_outputs_count"] = 1
		self.assertEqual(record_issues("ilL-Spec-Driver", driver), [])
		driver["usable_load_factor"] = 1.1
		self.assertIn(
			"usable_load_factor", {row["field"] for row in record_issues("ilL-Spec-Driver", driver)}
		)

	def test_sheet_accepts_full_watts_and_driver_defined_feed_capacity(self):
		spec = dict(
			item="SHEET",
			input_voltage="24V",
			input_protocol="PWM",
			led_package="TW",
			cct="Tunable White",
			sheet_width_ft=1,
			sheet_height_ft=2,
			total_sheet_watts=40,
			max_panels_per_feed=0,
		)
		self.assertEqual(record_issues("ilL-Spec-LED-Sheet", spec), [])
		spec["total_sheet_watts"] = float("nan")
		self.assertIn(
			"total_sheet_watts", {row["field"] for row in record_issues("ilL-Spec-LED-Sheet", spec)}
		)

	def test_ambiguous_option_codes_or_defaults_are_reported(self):
		options = [
			{"option_type": "CCT", "option_code": "30", "attribute_link": "3000K", "is_default": 1},
			{"option_type": "CCT", "option_code": "30", "attribute_link": "3500K", "is_default": 1},
		]
		issues = record_issues("ilL-Driver-Template", {"name": "driver", "allowed_options": options})
		self.assertEqual(len(issues), 2)
		self.assertTrue(
			all(row["record"] == "driver" and row["field"] == "allowed_options" for row in issues)
		)

	def test_sheet_csv_retains_full_panel_rating_protocol_cct_and_driver_associations(self):
		config = FixtureBuilderConfig(
			product_type="led-sheet",
			led_sheet_specs=[
				LedSheetSpecDef(
					item_code="SNOW",
					led_package="TW",
					cct="Tunable White",
					input_protocol="PWM",
					total_sheet_watts=40,
				)
			],
			led_sheet_templates=[LedSheetTemplateDef(template_code="Snowfield")],
			drivers=DriverDef(driver_specs=["PS-100"]),
		)
		with tempfile.TemporaryDirectory() as directory:
			path = gen_led_sheet_template.generate_specs(config, directory)
			with Path(path).open(encoding="utf-8-sig", newline="") as stream:
				row = next(csv.DictReader(stream))
			self.assertEqual(row["Total Sheet Watts"], "40")
			self.assertEqual(row["Required Input Protocol"], "PWM")
			self.assertEqual(row["CCT"], "Tunable White")
			path = gen_rel_driver_eligibility.generate(config, directory)
			with Path(path).open(encoding="utf-8-sig", newline="") as stream:
				row = next(csv.DictReader(stream))
			self.assertEqual(row["Template Type"], "ilL-LED-Sheet-Template")
			self.assertEqual(row["Product Template"], "Snowfield")
			self.assertEqual(row["Driver Spec"], "PS-100")
