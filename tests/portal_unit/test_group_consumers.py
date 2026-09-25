"""Pinned group production, stock/reopen and document behavior with framework doubles."""

import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint


class GroupConsumers(unittest.TestCase):
	def test_stock_and_reopen_use_verified_group_and_preserve_members(self):
		geometry = {"segments": [{"requested_length_mm": 1000, "end_type": "Endcap"}]}
		build = {
			"request": {"family": "LED Tape", "template": "T", "members": [geometry]},
			"components": [{"item_code": "WIRE", "stock_uom": "Foot", "qty": 11}],
		}
		adapter = types.SimpleNamespace(snapshot=MagicMock(return_value=build), description=lambda _: "Group")
		with load_service(ROOT + ".portal.group_display", {ROOT + ".api.fixture_group_bom": adapter}) as (
			module,
			_frappe,
		):
			self.assertEqual(module.stored_request(Record())["members"], [{"input": geometry}])
			self.assertEqual(
				module.stock_components(Record(configured_group="G")), [("Component", "WIRE", 11, "Foot")]
			)
			adapter.snapshot.side_effect = ValueError("tampered")
			with self.assertRaisesRegex(ValueError, "tampered"):
				module.stock_components(Record(configured_group="G"))

	def test_pinned_member_document_keeps_cuts_and_does_not_recalculate(self):
		group = {"request": {"family": "LED Neon", "template": "NEON"}}
		member = {
			"member_key": "M2",
			"geometry": {},
			"pricing_inputs": {},
			"build": {
				"computed": {
					"total_manufacturable_length_mm": 500,
					"segments": [{"segment_index": 1, "start_lead_length_inches": 72}],
				},
				"resolved_items": {"tape_spec": "ENGINE"},
			},
		}
		with load_service(ROOT + ".portal.build_documents") as (module, frappe):
			frappe._dict = Record
			doc = module.member_document(group, member)
			self.assertEqual(doc.manufacturable_length_mm, 500)
			self.assertEqual(doc.segments[0].start_lead_length_inches, 72)
			self.assertFalse(doc.include_power_supply)
			self.assertEqual(doc.tape_neon_template, "NEON")
			frappe.get_doc.assert_not_called()

	def test_group_snapshot_rejects_tampering(self):
		with load_service(ROOT + ".api.fixture_group_bom") as (module, _):
			build = {
				"engine_version": "fixture-group-1",
				"members": [{"member_key": "M1"}],
				"components": [{"qty": 1}],
			}
			doc = Record(config_hash=fingerprint(build), build_snapshot_json=json.dumps(build))
			self.assertEqual(module.snapshot(doc), build)
			build["components"][0]["qty"] = 2
			doc["build_snapshot_json"] = json.dumps(build)
			with self.assertRaisesRegex(ValueError, "pinned identity"):
				module.snapshot(doc)

	def test_work_order_covers_only_unplanned_demand_and_rolls_back_errors(self):
		with load_service(ROOT + ".api.build_artifacts") as (artifacts, boundary):
			with load_service(
				ROOT + ".api.manufacturing_order", {ROOT + ".api.build_artifacts": artifacts}
			) as (module, frappe):
				configured = Record(doctype="ilL-Configured-Group", name="G", bom="B")
				order = Record(name="SO", company="Company")
				row = Record(name="ROW", item_code="GROUP", qty=3, conversion_factor=1)
				build = {
					"members": [
						{"member_key": "M1", "build": {"cables": [{"role": "leader", "length_mm": 1828.8}]}}
					]
				}
				work = MagicMock(name="WO")
				work.name = "WO"
				frappe.get_doc.return_value = work
				frappe.get_meta = MagicMock()
				frappe.get_meta.return_value.has_field.return_value = True
				frappe.get_all.return_value = [
					Record(name="EXIST", production_item="GROUP", bom_no="B", qty=1, status="Draft")
				]
				with patch.object(module, "pinned_build", return_value=(configured, build)):
					module.create_for_line(order, row)
					data = frappe.get_doc.call_args.args[0]
					self.assertEqual(data["qty"], 2)
					self.assertEqual(data["sales_order_item"], "ROW")
					self.assertIn("1828.8", data["remarks"])
					self.assertEqual(data["ill_configured_group"], "G")
					frappe.get_all.return_value[0]["qty"] = 3
					self.assertFalse(module.create_for_line(order, row)["created"]["work_order"])
					frappe.get_all.return_value[0]["bom_no"] = "DIFFERENT"
					with self.assertRaisesRegex(ValueError, "reconcile"):
						module.create_for_line(order, row)
					boundary.db.rollback.assert_called_once_with(save_point="build_create_for_line")

	def test_order_material_snapshot_bom_mismatch_is_not_silently_rebuilt(self):
		adapter = types.SimpleNamespace(snapshot=lambda _: {"components": []})
		with (
			load_service(ROOT + ".api.manufacturing_order") as (module, frappe),
			patch.dict(sys.modules, {ROOT + ".api.fixture_group_bom": adapter}),
		):
			frappe.get_doc.return_value = Record(
				doctype="ilL-Configured-Group", configured_item="GROUP", bom="PINNED"
			)
			with self.assertRaisesRegex(ValueError, "pinned configured build"):
				module.pinned_build(Record(ill_configured_group="G", item_code="GROUP", ill_bom="OTHER"))
