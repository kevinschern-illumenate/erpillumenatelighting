"""Regression checks for legacy family generators against today's DocTypes."""

import csv
import tempfile
import unittest

from tools.fixture_builder.__main__ import generate_all, generate_all_led_sheet
from tools.fixture_builder.catalog_schema import build_schema
from tools.fixture_builder.config_schema import (
	FixtureBuilderConfig,
	LedSheetSpecDef,
	LedSheetTemplateDef,
	MountingAccessoryDef,
	TapeNeonAllowedOptionDef,
)
from tools.fixture_builder.generators import gen_tape_neon_template
from tools.fixture_builder.tests.test_generators import _castle_config
from tools.fixture_builder.tests.test_tape_neon_generators import _neon_config, _tape_config


class LegacyCatalogTests(unittest.TestCase):
	def read(self, path):
		with open(path, encoding="utf-8-sig", newline="") as handle:
			return list(csv.reader(handle))

	def test_legacy_webflow_columns_match_current_parent_and_children(self):
		schema = build_schema()["doctypes"]
		valid = set()
		for field in schema["ilL-Webflow-Product"]["fields"]:
			if field["fieldtype"] == "Table":
				valid.update(
					f"{child.get('label', child['fieldname'])} ({field['label']})"
					for child in schema[field["options"]]["fields"]
				)
			else:
				valid.add(field.get("label", field["fieldname"]))
		for config in (_castle_config(), _tape_config(), _neon_config()):
			with self.subTest(product=config.product_type), tempfile.TemporaryDirectory() as output:
				headers, *rows = self.read(generate_all(config, output)["ilL-Webflow-Product.csv"])
				self.assertFalse(set(headers) - valid)
				self.assertTrue(all(len(row) == len(headers) for row in rows))
				if config.product_type in {"tape", "neon"}:
					self.assertEqual(
						rows[0][headers.index("Tape / Neon Template")],
						config.tape_neon_templates[0].template_code,
					)
					self.assertEqual(rows[0][headers.index("Fixture Template")], "")

	def test_led_sheet_generation_includes_item_masters_and_valid_coverage_step(self):
		config = FixtureBuilderConfig(
			product_type="led-sheet",
			series_name="Example",
			led_sheet_specs=[LedSheetSpecDef(item_code="SHEET")],
			led_sheet_templates=[LedSheetTemplateDef(template_code="SHEET-TEMPLATE")],
		)
		with tempfile.TemporaryDirectory() as output:
			files = generate_all_led_sheet(config, output)
			headers, *rows = self.read(files["Item CSV.csv"])
			self.assertEqual(rows[0][headers.index("Item Code")], "SHEET")
			self.assertEqual(rows[0][headers.index("Default Unit of Measure")], "Nos")
			headers, *rows = self.read(files["ilL-Webflow-Product.csv"])
			steps = [row[headers.index("Option Type (Configurator Options)")] for row in rows]
			self.assertEqual(steps.count("Coverage"), 1)
			self.assertNotIn("Coverage Width", steps)

	def test_mounting_map_is_generated_for_tape_and_neon(self):
		config = _neon_config()
		config.mounting_accessories = [
			MountingAccessoryDef(mounting_method="Clip", accessory_item="ACC-CLIP")
		]
		with tempfile.TemporaryDirectory() as output:
			files = generate_all(config, output)
			headers, *rows = self.read(files["ilL-Rel-Mounting-Accessory-Map.csv"])
			self.assertEqual(rows[0][headers.index("Template Type")], "ilL-Tape-Neon-Template")
			self.assertEqual(rows[0][headers.index("Accessory Item")], "ACC-CLIP")

	def test_tape_options_have_aligned_lens_feed_and_active_columns(self):
		config = _neon_config()
		config.tape_neon_templates[0].allowed_options = [
			TapeNeonAllowedOptionDef(option_type="Lens Appearance", value="Frosted", is_active=False),
			TapeNeonAllowedOptionDef(option_type="Feed Direction", value="Side", feed_position="Start"),
		]
		with tempfile.TemporaryDirectory() as output:
			headers, *rows = self.read(gen_tape_neon_template.generate(config, output))
			self.assertTrue(all(len(row) == len(headers) for row in rows))
			self.assertEqual(rows[-2][headers.index("Lens Appearance (Allowed Options)")], "Frosted")
			self.assertEqual(rows[-2][headers.index("Is Active (Allowed Options)")], "0")
			self.assertEqual(rows[-1][headers.index("Feed Position (Allowed Options)")], "Start")

	def test_fixture_templates_link_the_generated_profile_spec(self):
		with tempfile.TemporaryDirectory() as output:
			headers, *rows = self.read(generate_all(_castle_config(), output)["ilL-Fixture-Template.csv"])
			self.assertTrue(all(len(row) == len(headers) for row in rows))
			self.assertEqual(rows[0][headers.index("Default Profile Spec")], "CH-CA02-WH")

	def test_every_expanded_component_spec_has_an_item_and_variant_values(self):
		with tempfile.TemporaryDirectory() as output:
			files = generate_all(_castle_config(), output)
			items = set()
			for filename in ("Item CSV.csv", "Item Variants.csv"):
				headers, *rows = self.read(files[filename])
				items.update(
					row[headers.index("Item Code")] for row in rows if row[headers.index("Item Code")]
				)
				if filename == "Item Variants.csv":
					self.assertTrue(
						all(row[headers.index("Attribute Value (Variant Attributes)")] for row in rows)
					)
					self.assertTrue(
						all(
							row[headers.index("Variant Of")] in items
							for row in rows
							if row[headers.index("Item Code")]
						)
					)
			for filename in ("ilL-Spec-Profile.csv", "ilL-Spec-Lens.csv", "ilL-Spec-Accessory.csv"):
				_, *rows = self.read(files[filename])
				self.assertTrue(all(row[0] in items for row in rows if row[0]), filename)
			self.assertIn("Item Attribute.csv", files)

	def test_legacy_import_headers_stay_in_sync_with_doctypes(self):
		schema = build_schema()["doctypes"]
		aliases = {"Item CSV": "Item", "Item Variants": "Item"}
		for config in (_castle_config(), _tape_config(), _neon_config()):
			with self.subTest(product=config.product_type), tempfile.TemporaryDirectory() as output:
				for filename, path in generate_all(config, output).items():
					doctype = aliases.get(filename[:-4], filename[:-4])
					valid = {"ID", "name"}
					for field in schema[doctype]["fields"]:
						if field["fieldtype"] == "Table":
							valid.update(
								f"{child.get('label', child['fieldname'])} ({field['label']})"
								for child in schema[field["options"]]["fields"]
							)
						else:
							valid.update((field["fieldname"], field.get("label", field["fieldname"])))
					headers, *rows = self.read(path)
					self.assertFalse(set(headers) - valid, f"{filename}: {set(headers) - valid}")
					self.assertTrue(all(len(row) == len(headers) for row in rows), filename)
