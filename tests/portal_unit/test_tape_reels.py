"""Bulk stock is continuous material, independent of the installation circuit plan."""

import copy
import types
import unittest

from test_services import ROOT, Record, load_service


class TapeReels(unittest.TestCase):
	def test_units_normalize_and_assembly_controls_are_rejected(self):
		with load_service(ROOT + ".api.tape_reels") as (reels, frappe):
			frappe.db.exists.return_value = True
			a = {"tape_length_value": 50, "tape_length_unit": "ft"}
			b = {"tape_length_value": 15240, "tape_length_unit": "mm"}
			reels.validate_request(a, None, "led-hd-sw")
			reels.validate_request(b, None, "led-hd-sw")
			self.assertEqual(a, b)
			for changed in (
				{"lead_length_inches": 1},
				{"override_max_run_ft": 10},
				{"end_type": "Jumper"},
				{"tape_length_value": float("nan")},
				{"tape_length_unit": "yards"},
			):
				with self.subTest(changed=changed), self.assertRaises(ValueError):
					reels.validate_request({**a, **changed}, None, "led-hd-sw")
			frappe.db.exists.return_value = False
			with self.assertRaisesRegex(ValueError, "active LED Tape"):
				reels.validate_request(a, None, "Neon")

	def test_electrical_splits_do_not_create_physical_cables_or_cuts(self):
		with load_service(ROOT + ".api.tape_neon_build") as (build, frappe):
			frappe.db.get_value.side_effect = lambda doctype, code, *args, **kwargs: Record(
				stock_uom="Foot" if code == "TAPE" else "Nos", disabled=0
			)
			with load_service(ROOT + ".api.tape_reels", {ROOT + ".api.tape_neon_build": build}) as (reels, _):
				result = {
					"computed": {"manufacturable_length_mm": 15240, "runs_count": 3},
					"resolved_items": {
						"tape_item": "TAPE",
						"leader_cable_item": "WIRE",
						"driver_plan": {"drivers": [{"driver_item": "DRIVER", "qty": 2}]},
					},
				}
				before = copy.deepcopy(result)
				rows, cables = reels.physical_manifest(result)
				self.assertEqual(cables, [])
				self.assertEqual([(r["item_code"], r["qty"]) for r in rows], [("TAPE", 50), ("DRIVER", 2)])
				self.assertEqual(result, before)

	def test_reel_price_uses_materials_and_optional_supplies_once(self):
		with load_service(
			ROOT + ".api.tape_neon_pricing",
			{
				ROOT + ".api.tape_neon_configurator": types.SimpleNamespace(
					_compute_template_tape_neon_pricing=lambda *args: self.fail(
						"Assembly price used for reel"
					)
				)
			},
		) as (pricing, _):
			pricing.selling_amount = lambda item, qty: qty * (3 if item == "TAPE" else 40)
			result = {
				"computed": {"ordering_mode": "BULK_REEL"},
				"resolved_items": {},
				"components": [{"item_code": "TAPE", "qty": 50}, {"item_code": "DRIVER", "qty": 2}],
			}
			self.assertEqual(pricing.price_result(result, "T1")["computed"]["total_price_msrp"], 230)
