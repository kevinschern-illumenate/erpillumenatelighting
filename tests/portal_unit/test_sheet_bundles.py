"""Sheet safety/identity regressions. Frappe calls use explicit boundary doubles."""

import copy
import json
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.led_sheet_math import normalize_dimension


class SheetBundles(unittest.TestCase):
	def candidate(self, **values):
		return {
			"item_code": "PS",
			"max_wattage": 200,
			"max_wattage_per_output": 100,
			"outputs_count": 2,
			"usable_load_factor": 0.8,
			"cost": 12,
			**values,
		}

	def result(self):
		return {
			"panels_needed": 6,
			"watts_per_panel": 20,
			"include_power_supply": True,
			"coverage_width_ft": 3.0,
			"coverage_height_ft": 4.0,
			"msrp": 500,
			"pricing": {"total_msrp": 500},
			"total_msrp": 500,
		}

	def setup_engine(self, engine, frappe):
		frappe.db.get_value.return_value = Record(stock_uom="Nos", disabled=0)
		template = Record(name="Snowfield", jumper_cable_item="JUMPER", leader_cable_item="LEADER")
		spec = Record(item="PANEL", input_voltage="24V", max_panels_per_feed=0)
		revisions = {"PS": Record(name="PS-SPEC", max_wattage=200)}
		return template, spec, patch.object(engine, "_drivers", return_value=([self.candidate()], revisions))

	def test_full_watts_and_per_output_derating_even_with_multiple_outputs(self):
		with load_service(ROOT + ".api.led_sheet_bundle") as (engine, _):
			limit = engine.feed_limit(20, [self.candidate()])
			self.assertEqual(limit, 4)  # Not 10 panels at nameplate, nor average TW loading.
			groups = engine.electrical_groups(6, 20, limit)
			self.assertEqual([g["group_watts"] for g in groups], [80, 40])
			self.assertEqual(sum(g["sheet_count"] for g in groups), 6)
			with self.assertRaisesRegex(ValueError, "one panel at full wattage"):
				engine.feed_limit(81, [self.candidate()])

	def test_power_count_is_supplies_not_outputs(self):
		with load_service(ROOT + ".api.led_sheet_bundle") as (engine, frappe):
			template, spec, drivers = self.setup_engine(engine, frappe)
			with drivers:
				result = engine.resolve(self.result(), template, spec)
			self.assertEqual(result["total_groups"], 2)
			self.assertEqual(result["power_supplies"], [{"driver_item": "PS", "qty": 1}])
			counts = {row["role"]: row["qty"] for row in result["components"]}
			self.assertEqual(counts, {"panels": 6, "jumpers": 12, "leaders": 2, "power": 1})

	def test_string_false_excludes_power_but_retains_actual_feed_requirements(self):
		with load_service(ROOT + ".api.led_sheet_bundle") as (engine, frappe):
			template, spec, drivers = self.setup_engine(engine, frappe)
			result = {**self.result(), "include_power_supply": "false"}
			with drivers:
				engine.resolve(result, template, spec)
			self.assertEqual(result["power_plan"]["status"], "excluded")
			self.assertEqual(len(result["power_plan"]["requirements"]), 2)
			self.assertFalse(any(row["role"] == "power" for row in result["components"]))

	def test_explicit_feed_limit_allows_excluded_supply_without_purchasable_driver(self):
		with load_service(ROOT + ".api.led_sheet_bundle") as (engine, frappe):
			template, spec, _ = self.setup_engine(engine, frappe)
			spec["max_panels_per_feed"] = 3
			with patch.object(engine, "_drivers", side_effect=AssertionError("No driver lookup is needed")):
				result = engine.resolve({**self.result(), "include_power_supply": False}, template, spec)
			self.assertEqual([row["group_watts"] for row in result["groups"]], [60, 60])
			self.assertEqual(result["power_plan"]["drivers"], [])

	def test_snapshot_prices_cannot_rename_build_but_dimensions_and_power_can(self):
		with load_service(ROOT + ".api.led_sheet_bundle") as (engine, frappe):
			template, spec, drivers = self.setup_engine(engine, frappe)
			with drivers:
				result = engine.resolve(self.result(), template, spec)
			first = engine.seal(copy.deepcopy(result), spec)
			result.update(msrp=999, total_msrp=999, pricing={"total_msrp": 999})
			second = engine.seal(copy.deepcopy(result), spec)
			self.assertEqual(first["config_hash"], second["config_hash"])
			self.assertNotIn("msrp", second["build_snapshot_json"])
			result["coverage_width_ft"] = 3.1
			self.assertNotEqual(first["config_hash"], engine.seal(copy.deepcopy(result), spec)["config_hash"])
			result["coverage_width_ft"] = 3.0
			result["power_plan"]["drivers"][0]["driver_item"] = "PS2"
			self.assertNotEqual(first["config_hash"], engine.seal(result, spec)["config_hash"])

	def test_bulk_cable_is_not_silently_priced_as_one_foot_per_assembly(self):
		with load_service(ROOT + ".api.led_sheet_bundle") as (engine, frappe):
			frappe.db.get_value.return_value = Record(stock_uom="Foot", disabled=0)
			with self.assertRaisesRegex(ValueError, "explicit length mapping"):
				engine._component("BULK", 2, "leaders")

	def test_bom_cannot_be_reused_for_other_size_or_wrong_component_quantity(self):
		with load_service(ROOT + ".api.led_sheet_bundle") as (engine, frappe):
			template, spec, drivers = self.setup_engine(engine, frappe)
			with drivers:
				result = engine.seal(engine.resolve(self.result(), template, spec), spec)
			doc = Record(
				engine_version=engine.ENGINE_VERSION,
				bundle_mode="Bundle",
				config_hash=result["config_hash"],
				build_snapshot_json=result["build_snapshot_json"],
			)
			bom = MagicMock(item=engine.item_code(doc), docstatus=1, is_active=1, quantity=1)
			bom.items = [Record(row) for row in engine.bom_items(doc)]
			engine.assert_bom(doc, bom)
			bom.items[0]["qty"] -= 1
			with self.assertRaisesRegex(ValueError, "pinned bundle"):
				engine.assert_bom(doc, bom)
			changed = json.loads(doc.build_snapshot_json)
			changed["coverage_width_ft"] = 99
			doc["build_snapshot_json"] = json.dumps(changed)
			with self.assertRaisesRegex(ValueError, "immutable identity"):
				engine.item_code(doc)

	def test_strict_dimensions(self):
		self.assertEqual(normalize_dimension(36, "in"), 3)
		for value, unit in ((float("nan"), "ft"), (float("inf"), "in"), (3, "yards"), (True, "ft")):
			with self.subTest(value=value, unit=unit), self.assertRaises(ValueError):
				normalize_dimension(value, unit)

	def test_portal_calculation_counts_complete_bundle_once(self):
		with load_service(ROOT + ".api.led_sheet_bundle") as (engine, db):
			template, spec, drivers = self.setup_engine(engine, db)
			template.update(
				is_active=1,
				sku_series_code="SNOW",
				price_per_sheet_msrp=10,
				allowed_specs=[Record(spec="PANEL", is_active=1)],
			)
			spec.update(
				is_active=1,
				sheet_width_ft=1,
				sheet_height_ft=2,
				sheet_area_sqft=2,
				total_sheet_watts=20,
				watts_per_sqft=10,
			)
			with load_service(ROOT + ".api.led_sheet_configurator") as (api, frappe):
				template["allowed_options"] = [
					Record(
						option_type=key,
						attribute_link=key,
						option_code="A",
						msrp_adder=1,
						is_active=1,
						is_default=1,
					)
					for key in api.OPTION_FIELD_BY_TYPE
				]
				frappe.get_doc.side_effect = lambda doctype, name: (
					template if doctype.endswith("Template") else spec
				)
				with (
					drivers,
					patch.object(api, "led_sheet_bundle", engine),
					patch.object(api, "_item_name", side_effect=lambda code: code),
					patch.object(
						api,
						"_item_price",
						side_effect=lambda code: {"JUMPER": 2, "LEADER": 3, "PS": 50}[code],
					),
				):
					result = api._calculate_sheet(
						"Snowfield", "PANEL", coverage_width_ft=3, coverage_height_ft=4
					)
					with patch.object(
						api, "_item_price", side_effect=AssertionError("Public preview read prices")
					):
						public = api._calculate_sheet(
							"Snowfield", "PANEL", coverage_width_ft=3, coverage_height_ft=4, commercial=False
						)
					self.assertNotIn("pricing", public)
					self.assertNotIn("msrp", public)
					self.assertEqual(public["config_hash"], result["config_hash"])
				self.assertEqual(
					result["msrp"], 170
				)  # 90 panels/options + 24 jumpers + 6 leaders + 50 supply.
				self.assertEqual(result["pricing"]["total_msrp"], result["msrp"])
				self.assertNotIn("unit_price", result["build_snapshot_json"])
				self.assertEqual(sum(g["group_watts"] for g in result["groups"]), 120)

	def test_identical_lines_cannot_steal_ambiguous_legacy_accessories(self):
		with load_service(ROOT + ".api.led_sheet_configurator") as (api, _):
			line = Record(name="ROW1", configured_led_sheet="SH1", manufacturer_type="ILLUMENATE")
			other = Record(name="ROW2", configured_led_sheet="SH1", manufacturer_type="ILLUMENATE")
			accessory = Record(manufacturer_type="ACCESSORY", notes="Jumpers for LED Sheet SH1")
			schedule = Record(lines=[line, other, accessory])
			with self.assertRaisesRegex(ValueError, "ambiguous line ownership"):
				api._legacy_line_marker(schedule, line)
			schedule["lines"] = [line, accessory]
			self.assertEqual(api._legacy_line_marker(schedule, line), "for LED Sheet line ROW1")
			self.assertEqual(accessory.notes, "Jumpers for LED Sheet line ROW1")
			schedule["lines"].append(other)
			self.assertEqual(api._legacy_line_marker(schedule, other), "for LED Sheet line ROW2")
			self.assertEqual(accessory.notes, "Jumpers for LED Sheet line ROW1")

	def test_failed_bom_rolls_back_partial_item_and_never_pins_it(self):
		helpers = types.SimpleNamespace(
			ILLUMENATE_BRAND="ilLumenate",
			_ensure_brand_exists=lambda name: None,
			_ensure_item_group_exists=lambda name: None,
		)
		with load_service(
			ROOT + ".api.led_sheet_bundle", {ROOT + ".api.manufacturing_generator": helpers}
		) as (engine, frappe):
			doc = MagicMock(name="SH1", configured_item=None, bom=None)
			frappe.db.exists.return_value = False
			frappe.db.get_value.side_effect = [Record(stock_uom="Nos", disabled=0), None]
			bom = MagicMock()
			bom.submit.side_effect = ValueError("Invalid component")
			frappe.get_doc.side_effect = [MagicMock(), bom]
			with (
				patch.object(engine, "item_code", return_value="ILL-SHEET-HASH"),
				patch.object(engine, "bom_items", return_value=[]),
			):
				with self.assertRaisesRegex(ValueError, "Invalid component"):
					engine.ensure_artifacts(doc)
			frappe.db.rollback.assert_called_once_with(save_point="sheet_artifacts")
			doc.save.assert_not_called()


if __name__ == "__main__":
	unittest.main()
