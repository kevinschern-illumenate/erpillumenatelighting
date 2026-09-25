"""Actual material/electrical services with explicit Frappe database doubles."""

import copy
import json
import types
import unittest

from test_services import ROOT, Record, load_service


class TapeNeonBuilds(unittest.TestCase):
	def result(self):
		return {
			"product_category": "LED Tape",
			"selections": {},
			"resolved_items": {
				"tape_item": "TAPE",
				"leader_cable_item": "WIRE",
				"driver_plan": {"drivers": []},
			},
			"computed": {
				"max_run_ft_effective": 10,
				"segments": [
					{
						"manufacturable_length_mm": 1828.8,
						"start_lead_length_inches": 72,
						"end_feed_length_inches": 12,
						"end_type": "Jumper",
						"runs_count": 2,
						"runs": [
							{"run_watts": 20, "run_len_mm": 914.4},
							{"run_watts": 20, "run_len_mm": 914.4},
						],
					},
					{
						"manufacturable_length_mm": 304.8,
						"start_lead_length_inches": 12,
						"end_feed_length_inches": 0,
						"end_type": "Endcap",
						"runs_count": 1,
						"runs": [{"run_watts": 10, "run_len_mm": 304.8}],
					},
				],
			},
		}

	def test_physical_jumper_counted_once_and_additional_feed_is_separate(self):
		with load_service(ROOT + ".api.tape_neon_build") as (engine, frappe):
			frappe.db.get_value.return_value = Record(stock_uom="Foot", disabled=0)
			components, cables = engine.physical_manifest(self.result(), additional_feed_mm=304.8)
			self.assertEqual([r["role"] for r in cables], ["leader", "jumper", "additional feed"])
			self.assertAlmostEqual(sum(r["qty"] for r in cables), 8)
			self.assertAlmostEqual(sum(r["qty"] for r in components if r["role"] == "light engine"), 7)
			with self.assertRaisesRegex(ValueError, "additional split-run feeds"):
				engine.physical_manifest(self.result())

	def test_conflicting_jumper_ownership_and_invalid_lengths_fail(self):
		with load_service(ROOT + ".api.tape_neon_build") as (engine, frappe):
			frappe.db.get_value.return_value = Record(stock_uom="Foot", disabled=0)
			result = self.result()
			result["computed"]["segments"][1]["start_lead_length_inches"] = 24
			with self.assertRaisesRegex(ValueError, "inherited start must match"):
				engine.physical_manifest(result, additional_feed_mm=304.8)
			for invalid in (float("nan"), -1, 0):
				result = self.result()
				result["computed"]["segments"][0]["manufacturable_length_mm"] = invalid
				with self.subTest(invalid=invalid), self.assertRaises(ValueError):
					engine.physical_manifest(result, additional_feed_mm=304.8)

	def test_jumper_connected_runs_share_output_and_enforce_total_run_limit(self):
		with load_service(ROOT + ".api.tape_neon_power") as (engine, _):
			computed = self.result()["computed"]
			before = copy.deepcopy(computed)
			runs = engine.connected_runs(computed)
			self.assertEqual([r["run_watts"] for r in runs], [20, 30])
			self.assertEqual([r["run_index"] for r in runs], [1, 2])
			self.assertEqual(computed, before)
			computed["max_run_ft_effective"] = 3
			with self.assertRaisesRegex(ValueError, "Jumper-connected length"):
				engine.connected_runs(computed)

	def test_mounting_item_requires_eligible_environment_and_real_quantity(self):
		with load_service(ROOT + ".api.tape_neon_build") as (engine, frappe):
			result = self.result()
			result["selections"] = {
				"mounting_accessory_item": "CLIP",
				"mounting_accessory_qty": 3,
				"environment_rating": "Wet",
				"mounting_accessory_unit_msrp": 0,
			}
			frappe.get_all.return_value = [Record(environment_rating="Dry")]
			with self.assertRaisesRegex(ValueError, "not approved"):
				engine.mounting_component(result, "T1")
			frappe.get_all.return_value = [Record(environment_rating="Wet")]
			frappe.db.get_value.return_value = Record(stock_uom="Nos", disabled=0)
			self.assertEqual(engine.mounting_component(result, "T1")["qty"], 3)
			self.assertNotIn("mounting_accessory_unit_msrp", result["selections"])
			result["selections"]["mounting_accessory_qty"] = 1.5
			with self.assertRaises(ValueError):
				engine.mounting_component(result, "T1")

	def test_pinned_materials_price_all_cables_mounts_and_supplies_once(self):
		pricing = types.SimpleNamespace(
			_compute_template_tape_neon_pricing=lambda *args: {"total_price_msrp": 100}
		)
		with load_service(
			ROOT + ".api.tape_neon_pricing", {ROOT + ".api.tape_neon_configurator": pricing}
		) as (engine, _):
			result = self.result()
			result["components"] = [
				{"item_code": "TAPE", "qty": 7, "role": "light engine"},
				{"item_code": "WIRE", "qty": 8, "role": "leader"},
				{"item_code": "CLIP", "qty": 3, "role": "mounting"},
				{"item_code": "DRIVER", "qty": 2, "role": "power"},
			]
			engine.selling_amount = lambda item, qty: {"WIRE": 2, "CLIP": 3, "DRIVER": 40}[item] * qty
			self.assertEqual(engine.price_result(result, "T1")["computed"]["total_price_msrp"], 205)

	def test_snapshot_detects_changed_materials(self):
		with load_service(ROOT + ".api.tape_neon_build") as (engine, _):
			build = {"components": [{"item_code": "WIRE", "qty": 6}]}
			doc = Record(
				build_schema_version=2,
				build_snapshot_json=json.dumps(build),
				config_hash=engine.fingerprint(build),
			)
			self.assertEqual(engine.snapshot(doc), build)
			build["components"][0]["qty"] = 5
			doc["build_snapshot_json"] = json.dumps(build)
			with self.assertRaisesRegex(ValueError, "verified physical"):
				engine.snapshot(doc)


if __name__ == "__main__":
	unittest.main()
