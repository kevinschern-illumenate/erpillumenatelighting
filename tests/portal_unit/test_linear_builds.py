"""Actual cable/identity/rollback service code with Frappe boundary doubles."""

import json
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service


class BuildDoc(Record):
	__setattr__ = dict.__setitem__

	def _renumber_user_segments(self):
		pass

	def before_save(self):
		pass

	def _generate_part_number(self):
		return "ILL-SH01-SW-EXAMPLE"


class LinearBuilds(unittest.TestCase):
	def fixture(self):
		return BuildDoc(
			name="PREVIEW",
			fixture_template="ILL-SH01-SW",
			leader_item="WIRE",
			is_multi_segment=1,
			segments=[
				Record(
					segment_index=1,
					start_leader_len_mm=1828.8,
					start_leader_item="WIRE",
					end_jumper_item="WIRE",
					end_jumper_len_mm=304.8,
				)
			],
			runs=[
				Record(run_index=1, leader_item="WIRE", leader_len_mm=300),
				Record(run_index=2, leader_item="WIRE", leader_len_mm=300),
			],
			flags=BuildDoc(),
		)

	def test_initial_leader_jumper_and_extra_feed_are_separate_once(self):
		with load_service(ROOT + ".api.linear_build") as (engine, frappe):
			frappe.db.get_value.return_value = Record(stock_uom="Foot", disabled=0)
			cuts = engine.cable_manifest(self.fixture())
			self.assertEqual([r["role"] for r in cuts], ["leader", "additional feed", "jumper"])
			self.assertAlmostEqual(cuts[0]["qty"], 6)
			self.assertAlmostEqual(cuts[1]["qty"], 300 / 304.8)
			self.assertAlmostEqual(cuts[2]["qty"], 1)
			self.assertAlmostEqual(engine.cable_bom_rows(cuts)[0]["qty"], 7 + 300 / 304.8)

	def test_count_based_cable_needs_exact_approved_assembly_length(self):
		with load_service(ROOT + ".api.linear_build") as (engine, frappe):
			fixture = self.fixture()
			fixture.runs = fixture.runs[:1]
			fixture.segments[0]["end_jumper_len_mm"] = 0
			frappe.db.get_value.return_value = Record(
				stock_uom="Nos", disabled=0, ill_cable_assembly_length_mm=1828.8
			)
			self.assertEqual(engine.cable_manifest(fixture)[0]["qty"], 1)
			frappe.db.get_value.return_value["ill_cable_assembly_length_mm"] = 300
			with self.assertRaisesRegex(ValueError, "exact fixed-length assembly"):
				engine.cable_manifest(fixture)

	def test_power_override_and_full_geometry_have_distinct_identity(self):
		material = types.SimpleNamespace(
			build_fixture_bom_items=lambda doc: [
				{"item_code": "WIRE", "qty": 7, "uom": "Foot", "stock_uom": "Foot"}
			]
		)
		with load_service(ROOT + ".api.linear_build", {ROOT + ".api.manufacturing_generator": material}) as (
			engine,
			frappe,
		):
			frappe.db.get_value.return_value = Record(stock_uom="Foot", disabled=0)

			def calculate(power=True, override=None, geometry=6000):
				return engine.finish(
					self.fixture(), {"length": geometry}, {"watts": 80}, {}, power, override, in_memory=True
				)

			original = calculate()
			self.assertEqual(original.name, calculate().name)
			self.assertNotEqual(original.name, calculate(False).name)
			self.assertNotEqual(original.name, calculate(override=20).name)
			self.assertNotEqual(original.name, calculate(geometry=6001).name)
			self.assertEqual(len(original.config_hash), 64)
			self.assertEqual(json.loads(original.build_snapshot_json)["cables"][0]["length_mm"], 1828.8)
			frappe.db.sql.assert_not_called()  # Preview does not create or lock a build.

	def test_color_channels_do_not_silently_become_independent_outputs(self):
		with load_service(ROOT + ".api.driver_catalog") as (catalog, _):
			driver = Record(name="TW", outputs_count=2, independent_outputs_count=0)
			with self.assertRaisesRegex(ValueError, "color/control channels"):
				catalog.independent_outputs(driver)
			driver["independent_outputs_count"] = 1
			self.assertEqual(catalog.independent_outputs(driver), 1)
			driver["independent_outputs_count"] = 3
			with self.assertRaises(ValueError):
				catalog.independent_outputs(driver)

	def test_returned_error_and_exception_both_rollback_the_complete_build(self):
		with load_service(ROOT + ".api.build_artifacts") as (artifacts, frappe):

			@artifacts.atomic_build
			def build(return_error):
				if return_error:
					return {"success": False, "error": "Row changed"}
				raise ValueError("BOM failed")

			self.assertFalse(build(True)["success"])
			with self.assertRaisesRegex(ValueError, "BOM failed"):
				build(False)
			self.assertEqual(frappe.db.rollback.call_count, 2)

	def test_reused_bom_must_be_submitted_and_match_all_pinned_stock_quantities(self):
		with load_service(ROOT + ".api.build_artifacts") as (artifacts, _):
			rows = [Record(item_code="WIRE", qty=6, stock_uom="Foot")]
			bom = MagicMock(item="ILL-CF-HASH", quantity=1, docstatus=1, is_active=1)
			bom.items = [Record(item_code="WIRE", qty=72, uom="Inch", stock_uom="Foot", stock_qty=6)]
			artifacts.assert_bom("ILL-CF-HASH", rows, bom)
			bom.docstatus = 0
			with self.assertRaisesRegex(ValueError, "pinned build"):
				artifacts.assert_bom("ILL-CF-HASH", rows, bom)
			bom.docstatus = 1
			bom.items[0]["stock_qty"] = 72
			with self.assertRaisesRegex(ValueError, "pinned build"):
				artifacts.assert_bom("ILL-CF-HASH", rows, bom)

	def test_engineering_additions_cannot_remove_required_materials_or_change_units(self):
		with load_service(ROOT + ".api.linear_build") as (engine, _):
			original = [{"item_code": "WIRE", "qty": 6, "stock_uom": "Foot"}]

			def lookup(code):
				return Record(stock_uom="Foot", disabled=0)

			rows = engine.validate_material_additions(original, [{"item_code": "WIRE", "qty": 7}], lookup)
			self.assertEqual(rows[0]["qty"], 7)
			for override in (
				[{"item_code": "WIRE", "qty": 5}],
				[{"item_code": "WIRE", "qty": 72, "uom": "Inch"}],
				[{"item_code": "WIRE", "qty": float("nan")}],
				[],
			):
				with self.subTest(override=override), self.assertRaises(ValueError):
					engine.validate_material_additions(original, override, lookup)

	def test_current_estimate_reprices_pinned_materials_without_changing_identity(self):
		pricing = types.SimpleNamespace(_calculate_pricing=MagicMock(return_value={"msrp_unit": 100}))
		selling = types.SimpleNamespace(selling_amount=lambda code, qty: qty * 4)
		with load_service(
			ROOT + ".api.linear_build",
			{
				ROOT + ".api.configurator_engine": pricing,
				ROOT + ".api.tape_neon_pricing": selling,
			},
		) as (engine, frappe):
			build = {
				"computed": {"tape_cut_length_mm": 2000},
				"resolved_items": {"driver_plan": {}},
				"components": [{"item_code": "WIRE", "qty": 8, "stock_uom": "Foot"}],
				"engineering_base_components": [{"item_code": "WIRE", "qty": 6, "stock_uom": "Foot"}],
				"engineering_material_additions": True,
			}
			doc = BuildDoc(
				build_schema_version=2,
				build_snapshot_json=engine.canonical_json(build),
				config_hash=engine.fingerprint(build),
			)
			original = dict(doc)
			frappe.db.get_value.return_value = Record(stock_uom="Foot", disabled=0)
			self.assertEqual(engine.current_estimate(doc), 108)
			pricing._calculate_pricing.return_value = {"msrp_unit": 120}
			self.assertEqual(engine.current_estimate(doc), 128)
			self.assertEqual(dict(doc), original)
			self.assertEqual(pricing._calculate_pricing.call_args.args[2], build["computed"])
			frappe.db.get_value.return_value = Record(stock_uom="Meter", disabled=0)
			with self.assertRaisesRegex(ValueError, "stock UOM"):
				engine.current_estimate(doc)


if __name__ == "__main__":
	unittest.main()
