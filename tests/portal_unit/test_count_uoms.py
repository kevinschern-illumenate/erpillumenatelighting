"""Configured products default to Ea; component quantities retain their stock units."""

import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.configuration_contract import cable_stock_quantity


class CountUoms(unittest.TestCase):
	def fixture(self):
		return Record(
			build_schema_version=2,
			is_multi_segment=1,
			profile_item="CHANNEL",
			lens_item="LENS",
			endcap_item_start="FEED",
			endcap_item_end="CAP",
			mounting_item="CLIP",
			segments=[
				Record(
					start_endcap_type="Feed-Through",
					end_endcap_type="Solid",
					end_type="Endcap",
					tape_cut_len_mm=304.8,
				)
				for _ in range(2)
			],
			drivers=[Record(driver_item="DRIVER", driver_qty=1)],
			cable_manifest_json="[]",
		)

	def test_linear_bom_preserves_count_uoms_and_length_quantities(self):
		with load_service(ROOT + ".api.manufacturing_generator") as (engine, frappe):
			for uom in ("Ea", "ea", "Nos", "Unit", "Each"):
				with (
					self.subTest(uom=uom),
					patch.object(engine, "_get_tape_item", return_value="TAPE"),
					patch.object(engine, "_calculate_mounting_quantity", return_value=4),
				):
					frappe.db.get_value.side_effect = lambda doctype, code, field: (
						"Foot" if code == "TAPE" else uom
					)
					rows = {row["item_code"]: row for row in engine.build_fixture_bom_items(self.fixture())}
					for code, qty in {
						"CHANNEL": 2,
						"LENS": 2,
						"FEED": 3,
						"CAP": 3,
						"CLIP": 4,
						"DRIVER": 1,
					}.items():
						self.assertEqual(
							rows[code], {"item_code": code, "qty": qty, "uom": uom, "stock_uom": uom}
						)
					self.assertEqual(
						rows["TAPE"], {"item_code": "TAPE", "qty": 2, "uom": "Foot", "stock_uom": "Foot"}
					)

	def test_linear_bom_identifies_incompatible_component(self):
		with load_service(ROOT + ".api.manufacturing_generator") as (engine, frappe):
			for uom in ("Meter", "Box", None):
				with self.subTest(uom=uom):
					frappe.db.get_value.return_value = uom
					with self.assertRaisesRegex(ValueError, f"CHANNEL.*{uom}"):
						engine.build_fixture_bom_items(self.fixture())

	def test_tape_neon_and_sheet_components_accept_ea_and_keep_legacy_units(self):
		for service, function in (("tape_neon_build", "item_row"), ("led_sheet_bundle", "_component")):
			with load_service(ROOT + ".api." + service) as (engine, frappe):
				for uom in ("Ea", "ea", "Nos", "Unit", "Each"):
					with self.subTest(service=service, uom=uom):
						frappe.db.get_value.return_value = Record(stock_uom=uom, disabled=0)
						row = getattr(engine, function)("COMPONENT", 3, "mounting")
						self.assertEqual((row["qty"], row["uom"], row["stock_uom"]), (3, uom, uom))
				frappe.db.get_value.return_value = Record(stock_uom="Foot", disabled=0)
				with self.assertRaises(ValueError):
					getattr(engine, function)("COMPONENT", 3, "mounting")

	def test_counted_cable_still_requires_an_exact_assembly_length(self):
		for uom in ("Ea", "ea", "Nos", "Unit", "Each"):
			with self.subTest(uom=uom):
				self.assertEqual(cable_stock_quantity(72, "in", uom, assembly_length_mm=1828.8), 1)
				with self.assertRaisesRegex(ValueError, "exact fixed-length assembly"):
					cable_stock_quantity(72, "in", uom)
				with self.assertRaisesRegex(ValueError, "exact fixed-length assembly"):
					cable_stock_quantity(72, "in", uom, assembly_length_mm=300)

	def test_bulk_tape_rejects_ea_even_with_an_assembly_length(self):
		with load_service(ROOT + ".api.tape_neon_build") as (build, frappe):
			frappe.db.get_value.return_value = Record(
				stock_uom="Ea",
				disabled=0,
				ill_cable_assembly_length_mm=15240,
			)
			with load_service(ROOT + ".api.tape_reels", {ROOT + ".api.tape_neon_build": build}) as (reels, _):
				with self.assertRaisesRegex(ValueError, "length-based stock UOM"):
					reels.physical_manifest(
						{
							"computed": {"manufacturable_length_mm": 15240},
							"resolved_items": {"tape_item": "TAPE"},
						}
					)


class ConfiguredItemUoms(unittest.TestCase):
	def test_new_linear_tape_and_neon_items_default_to_ea(self):
		snapshot = types.SimpleNamespace(snapshot=lambda doc: {}, current_estimate=lambda doc: 100)
		with (
			load_service(
				ROOT + ".api.manufacturing_generator",
				{
					ROOT + ".api.linear_build": snapshot,
					ROOT + ".api.tape_neon_build": snapshot,
				},
			) as (engine, frappe),
			patch.object(engine, "_ensure_item_group_exists"),
			patch.object(engine, "_ensure_brand_exists"),
			patch.object(engine, "_generate_item_description", return_value="Linear fixture"),
			patch.object(engine, "_create_item_price_at_msrp"),
		):
			for category in ("Linear Fixture", "LED Tape", "LED Neon"):
				with self.subTest(category=category):
					frappe.get_doc.reset_mock()
					frappe.db.exists.side_effect = None
					frappe.db.exists.return_value = False
					frappe.db.get_value.side_effect = lambda doctype, key, *a, **k: (
						None if isinstance(key, dict) else "Fixture template"
					)
					linear = category == "Linear Fixture"
					doc = Record(
						doctype="ilL-Configured-Fixture" if linear else "ilL-Configured-Tape-Neon",
						name="ILL-CF-" + "a" * 64 if linear else "ILL-CTN-00001",
						fixture_template="F1",
						build_schema_version=2,
						config_hash="a" * 64,
						part_number="READABLE",
						display_part_number="READABLE",
						product_category=category,
					)
					create = (
						engine._create_or_get_configured_item
						if linear
						else engine._create_or_get_configured_tape_neon_item
					)
					result = create(doc)
					self.assertTrue(result["success"], result)
					self.assertTrue(result["created"])
					self.assertEqual(result["item_code"], "READABLE")
					documents = [call.args[0] for call in frappe.get_doc.call_args_list]
					self.assertEqual(
						documents[0], {"doctype": "UOM", "uom_name": "Ea", "must_be_whole_number": 1}
					)
					self.assertEqual(documents[1]["doctype"], "Item")
					self.assertEqual(documents[1]["stock_uom"], "Ea")
					self.assertEqual(documents[1]["ill_build_id"], ("ILL-CF-" if linear else "ILL-TN-") + "a" * 64)
					# Reusing this build's existing Item must not change its stock UOM.
					frappe.get_doc.reset_mock()
					frappe.db.exists.side_effect = lambda doctype, code: code == "READABLE"
					frappe.db.get_value.side_effect = lambda doctype, key, *a, **k: (
						"READABLE" if isinstance(key, dict) else "Fixture template"
					)
					reused = create(doc)
					self.assertTrue(reused["skipped"])
					self.assertEqual(reused["item_code"], "READABLE")
					frappe.get_doc.assert_not_called()
					frappe.db.set_value.assert_not_called()

	def test_existing_ea_master_is_reused(self):
		with load_service(ROOT + ".api.manufacturing_generator") as (engine, frappe):
			frappe.db.exists.return_value = True
			engine._ensure_default_uom_exists()
			frappe.get_doc.assert_not_called()

	def helpers(self):
		return types.SimpleNamespace(
			ILLUMENATE_BRAND="ilLumenate",
			_ensure_brand_exists=lambda name: None,
			_ensure_item_group_exists=lambda name: None,
			_ensure_default_uom_exists=MagicMock(),
			_create_item_price_at_msrp=lambda *args: None,
		)

	def test_new_sheet_items_default_to_ea_and_legacy_items_can_be_reused(self):
		with load_service(
			ROOT + ".api.led_sheet_bundle",
			{
				ROOT + ".api.manufacturing_generator": self.helpers(),
			},
		) as (engine, frappe):
			for existing, uom in ((False, "Ea"), (True, "Nos")):
				with (
					self.subTest(existing=existing, uom=uom),
					patch.object(engine, "item_code", return_value="ILL-SHEET-HASH"),
					patch.object(engine, "bom_items", return_value=[]),
					patch.object(engine, "assert_bom"),
				):
					frappe.get_doc.reset_mock()
					frappe.db.exists.return_value = existing
					frappe.db.get_value.return_value = Record(stock_uom=uom, disabled=0)
					doc = MagicMock(configured_item=None, bom="BOM-SHEET")
					self.assertTrue(engine.ensure_artifacts(doc)["success"])
					items = [
						call.args[0]
						for call in frappe.get_doc.call_args_list
						if isinstance(call.args[0], dict)
					]
					self.assertEqual(len(items), 0 if existing else 1)
					if items:
						self.assertEqual(items[0]["stock_uom"], "Ea")

	def test_new_group_items_default_to_ea_and_legacy_items_can_be_reused(self):
		artifacts = types.SimpleNamespace(
			atomic_build=lambda fn: fn,
			ensure_bom=lambda *args: {"bom_name": "BOM-GROUP"},
		)
		with load_service(
			ROOT + ".api.fixture_group_bom",
			{
				ROOT + ".api.manufacturing_generator": self.helpers(),
				ROOT + ".api.build_artifacts": artifacts,
			},
		) as (engine, frappe):
			build = {
				"members": [{}, {}],
				"components": [],
				"total_watts": 10,
				"power_plan": {"requirements": []},
			}
			for existing, uom in ((False, "Ea"), (True, "Nos")):
				with (
					self.subTest(existing=existing, uom=uom),
					patch.object(engine, "snapshot", return_value=build),
					patch.object(engine, "description", return_value="Fixture group"),
				):
					frappe.get_doc.reset_mock()
					frappe.db.exists.return_value = existing
					frappe.db.get_value.return_value = Record(stock_uom=uom, disabled=0)
					doc = MagicMock(configured_item=None, config_hash="a" * 64)
					result = engine.ensure_artifacts(doc, msrp=100)
					self.assertEqual(result["bom"], "BOM-GROUP")
					if existing:
						frappe.get_doc.assert_not_called()
					else:
						self.assertEqual(frappe.get_doc.call_args.args[0]["stock_uom"], "Ea")


if __name__ == "__main__":
	unittest.main()
