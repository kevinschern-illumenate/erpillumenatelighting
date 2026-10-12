"""Group intent/identity, real power allocation, cut preservation and pinned materials."""

import copy
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint
from illumenate_lighting.illumenate_lighting.api.group_contract import merge_components, normalize


def request():
	return {
		"family": "Linear Fixture",
		"template": "ILL-SH01-SW",
		"shared": {"finish_code": "White"},
		"power": {"include_power_supply": True},
		"members": [
			{
				"member_id": str(i),
				"label": label,
				"input": {
					"segments": [
						{
							"length_value": length,
							"length_unit": "ft",
							"start_leader_cable_length_mm": leader * 304.8,
							"start_feed_direction": "End",
							"start_power_feed_type": "Wire",
							"end_type": "Endcap",
						}
					]
				},
			}
			for i, (label, length, leader) in enumerate(
				(("Long", 20, 6), ("Short", 5, 3), ("Longest", 25, 2))
			)
		],
	}


class GroupContract(unittest.TestCase):
	def test_l1_independent_members_and_unit_order_label_quantity_identity(self):
		first = request()
		normal = normalize(first)
		second = copy.deepcopy(first)
		second.update(qty=2, view="wizard")
		second["members"].reverse()
		for row in second["members"]:
			row.update(member_id="new", label="Renamed")
			segment = row["input"]["segments"][0]
			segment["length_value"] *= 304.8
			segment["length_unit"] = "mm"
		self.assertEqual(normal, normalize(second))
		self.assertAlmostEqual(
			sum(m["segments"][0]["requested_length_mm"] for m in normal["members"]), 50 * 304.8
		)
		self.assertAlmostEqual(
			sum(m["segments"][0]["start_leader_cable_length_mm"] for m in normal["members"]), 11 * 304.8
		)
		self.assertEqual(len(normal["members"]), 3)

	def test_false_forms_and_electrical_policy_are_in_identity(self):
		base = request()
		included = fingerprint(normalize(base))
		for value in (False, 0, "0", "false", "off"):
			base["power"]["include_power_supply"] = value
			self.assertFalse(normalize(base)["power"]["include_power_supply"])
			self.assertNotEqual(included, fingerprint(normalize(base)))
		base["power"]["override_max_run_ft"] = float("nan")
		with self.assertRaises(ValueError):
			normalize(base)

	def test_reject_mixed_template_member_specs_reels_and_cross_member_jumpers(self):
		for mutate in (
			lambda r: r["members"][0].update(template="Other"),
			lambda r: r["members"][0]["input"].update(finish_code="Black"),
			lambda r: r["members"][0]["input"].update(ordering_mode="BULK_REEL"),
			lambda r: r["members"][0]["input"]["segments"][-1].update(end_type="Jumper"),
			lambda r: r["members"][0]["input"]["segments"][0].update(length_value=float("inf")),
		):
			r = request()
			mutate(r)
			with self.assertRaises(ValueError):
				normalize(r)

	def test_sheet_areas_normalize_separately_and_reject_override(self):
		r = {
			"family": "LED Sheet",
			"template": "Snowfield",
			"shared": {"spec": "S"},
			"members": [
				{
					"input": {
						"coverage_width_value": 304.8,
						"coverage_width_unit": "mm",
						"coverage_height_ft": 2,
					}
				},
				{"input": {"coverage_width_ft": 2, "coverage_height_ft": 3}},
			],
		}
		areas = normalize(r)["members"]
		self.assertEqual(
			areas,
			[
				{"coverage_width_ft": 1, "coverage_height_ft": 2},
				{"coverage_width_ft": 2, "coverage_height_ft": 3},
			],
		)
		r["power"] = {"override_max_run_ft": 2}
		with self.assertRaisesRegex(ValueError, "Sheet areas"):
			normalize(r)

	def test_component_merge_preserves_operation_uom_and_warehouse(self):
		row = {"item_code": "WIRE", "qty": 6, "uom": "Foot", "stock_uom": "Foot", "operation": "Cut"}
		rows = merge_components([row, {**row, "qty": 3}, {**row, "qty": 2, "operation": "Assembly"}])
		self.assertEqual(sorted(r["qty"] for r in rows), [2, 9])


class GroupCalculation(unittest.TestCase):
	def test_failed_artifact_build_rolls_back_before_handoff(self):
		from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json

		build = {"engine_version": "group-1", "members": [], "power_plan": {"allocations": []}}
		calculation = types.SimpleNamespace(
			calculate=lambda _: {
				"build": build,
				"input_hash": "I",
				"config_hash": "H",
				"build_snapshot_json": canonical_json(build),
				"pricing": {"msrp_unit": 1},
			}
		)
		access = types.SimpleNamespace(register_configured_record_handoff=MagicMock())
		with load_service(ROOT + ".api.build_artifacts") as (atomic, db_frappe):
			deps = {
				ROOT + ".api.build_artifacts": atomic,
				ROOT + ".api.fixture_group_configurator": calculation,
				ROOT + ".portal.access": access,
			}
			with load_service(ROOT + ".api.fixture_group_bom", deps) as (service, frappe):
				# Groups are on by default; a site can turn them off.
				frappe.conf["ill_portal_fixture_groups"] = False
				with self.assertRaises(PermissionError):
					service.persist(request())
				frappe.get_doc.assert_not_called()
				db_frappe.db.rollback.reset_mock()
				frappe.conf["ill_portal_fixture_groups"] = 1
				frappe.db.get_value.return_value = None
				doc = MagicMock()
				frappe.get_doc.return_value = doc
				with (
					patch.object(
						service, "ensure_artifacts", side_effect=ValueError("Component Item missing")
					),
					self.assertRaisesRegex(ValueError, "Component Item"),
				):
					service.persist(request())
				doc.insert.assert_called_once()
				access.register_configured_record_handoff.assert_not_called()
				db_frappe.db.rollback.assert_called_once_with(save_point="build_persist")
				frappe.db.commit.assert_not_called()

	def preview(self, request, geometry):
		segment = geometry["segments"][0]
		length = segment["requested_length_mm"] / 304.8
		leader = segment["start_leader_cable_length_mm"] / 304.8

		def row(item, qty):
			return {"item_code": item, "qty": qty, "uom": "Foot", "stock_uom": "Foot"}

		return {
			"build": {
				"engine_version": "fixture-2",
				"components": [row("TAPE", length), row("WIRE", leader)],
				"cables": [{"item_code": "WIRE", "length_mm": leader * 304.8}],
			},
			"pricing_inputs": {},
			"circuits": [{"run_key": "1", "watts": length * 2}],
			"voltage": "24V",
			"output_protocol": "SW",
			"unit_msrp": 20 + length * 10,
		}

	def test_l1_one_parent_supply_no_member_duplicates_qty_one_bom(self):
		driver = {
			"item_code": "PS",
			"outputs_count": 3,
			"max_wattage": 150,
			"max_wattage_per_output": 80,
			"usable_load_factor": 1,
			"cost": 20,
		}
		catalog = types.SimpleNamespace(candidates=lambda *args: ([driver], {"PS": {"max_wattage": 150}}))
		items = types.SimpleNamespace(
			item_row=lambda item, qty, role: {
				"item_code": item,
				"qty": qty,
				"stock_uom": "Nos",
				"uom": "Nos",
				"role": role,
			}
		)
		prices = types.SimpleNamespace(selling_amount=lambda item, qty: 100 * qty)
		extras = {
			ROOT + ".api.driver_catalog": catalog,
			ROOT + ".api.tape_neon_build": items,
			ROOT + ".api.tape_neon_pricing": prices,
		}
		with load_service(ROOT + ".api.fixture_group_configurator", extras) as (engine, frappe):
			frappe.get_doc.return_value = Record(is_active=1)
			with patch.object(engine, "_preview_member", side_effect=self.preview):
				result = engine.calculate(request())
				self.assertEqual(result["pricing"]["msrp_unit"], 660)
				self.assertEqual(result["build"]["power_plan"]["drivers"], [{"driver_item": "PS", "qty": 1}])
				self.assertEqual(
					{c["item_code"]: c["qty"] for c in result["build"]["components"]},
					{"PS": 1, "TAPE": 50, "WIRE": 11},
				)
				self.assertEqual(
					sorted(
						round(m["build"]["cables"][0]["length_mm"], 6) for m in result["build"]["members"]
					),
					[609.6, 914.4, 1828.8],
				)
				r = request()
				r.update(qty=2)
				self.assertEqual(engine.calculate(r)["config_hash"], result["config_hash"])
				r["power"]["include_power_supply"] = False
				excluded = engine.calculate(r)
				self.assertEqual(excluded["pricing"]["msrp_unit"], 560)
				self.assertEqual(len(excluded["build"]["power_plan"]["requirements"]), 3)
				self.assertEqual(excluded["build"]["power_plan"]["drivers"], [])
				self.assertNotEqual(excluded["config_hash"], result["config_hash"])
				frappe.db.set_value.assert_not_called()

	def test_price_stripping_is_recursive(self):
		with load_service(ROOT + ".api.fixture_group_configurator") as (engine, _):
			self.assertEqual(
				engine.engineering(
					{"computed": {"total_price_msrp": 99, "length": 4}, "cables": [{"qty": 2, "cost": 9}]}
				),
				{"computed": {"length": 4}, "cables": [{"qty": 2}]},
			)


class GroupPresentation(unittest.TestCase):
	def engine(self):
		catalog = types.SimpleNamespace(candidates=lambda *args: ([], {}))
		items = types.SimpleNamespace(item_row=lambda item, qty, role: {"item_code": item, "qty": qty})
		prices = types.SimpleNamespace(selling_amount=lambda item, qty: 0)
		return load_service(
			ROOT + ".api.fixture_group_configurator",
			{
				ROOT + ".api.driver_catalog": catalog,
				ROOT + ".api.tape_neon_build": items,
				ROOT + ".api.tape_neon_pricing": prices,
			},
		)

	def test_runs_are_summarized_in_dealer_order_with_their_labels(self):
		with self.engine() as (engine, frappe):
			frappe.get_doc.return_value = Record(is_active=1)
			with patch.object(engine, "_preview_member", side_effect=GroupCalculation.preview.__get__(self)):
				r = request()
				r["power"]["include_power_supply"] = False
				runs = engine.calculate(r)["runs"]
		self.assertEqual([row["label"] for row in runs], ["Long", "Short", "Longest"])
		self.assertEqual([round(row["requested_length_mm"]) for row in runs], [6096, 1524, 7620])
		self.assertEqual([round(row["leader_length_mm"], 1) for row in runs], [1828.8, 914.4, 609.6])
		self.assertEqual({row["segments"] for row in runs}, {1})
		self.assertEqual([row["watts"] for row in runs], [40, 10, 50])

	def test_a_failing_run_is_named_and_preview_reports_it_without_a_server_error(self):
		def preview(_request, geometry):
			raise ValueError("Length exceeds the maximum")

		with self.engine() as (engine, frappe):
			frappe.get_doc.return_value = Record(is_active=1)
			frappe.conf["ill_portal_fixture_groups"] = True
			with patch.object(engine, "_preview_member", side_effect=preview):
				with self.assertRaisesRegex(ValueError, "^Short: Length exceeds"):
					engine.calculate(request())
				extras = {
					ROOT + ".api.pricing_utils": types.SimpleNamespace(get_tier_price_for_customer=dict),
					ROOT + ".portal.access": types.SimpleNamespace(require_catalog_access=lambda: None),
				}
				with patch.dict(sys.modules, extras):
					result = engine.preview(request())
		self.assertFalse(result["success"])
		self.assertIn("Short: Length exceeds", result["error"])

	def test_only_included_power_limits_the_number_of_circuits(self):
		def preview(_request, geometry):
			return {
				**GroupCalculation.preview(self, _request, geometry),
				"circuits": [{"run_key": str(i), "watts": 5} for i in range(1, 6)],
			}

		with self.engine() as (engine, frappe):
			frappe.get_doc.return_value = Record(is_active=1)
			with patch.object(engine, "_preview_member", side_effect=preview):
				with self.assertRaisesRegex(ValueError, "up to 12 circuits"):
					engine.calculate(request())
				r = request()
				r["power"]["include_power_supply"] = False
				plan = engine.calculate(r)["build"]["power_plan"]
		self.assertEqual((plan["status"], len(plan["requirements"])), ("excluded", 15))

	def test_descriptions_read_as_runs_and_use_saved_labels(self):
		build = {
			"request": {
				"family": "Linear Fixture",
				"power": {"include_power_supply": True, "separate_supply_line": True},
			},
			"members": [
				{
					"member_key": "M1",
					"geometry": {
						"segments": [
							{"requested_length_mm": 6096, "start_leader_cable_length_mm": 1828.8},
							{"requested_length_mm": 914.4},
						]
					},
				},
				{"member_key": "M2", "geometry": {"segments": [{"requested_length_mm": 1524}]}},
			],
		}
		with load_service(ROOT + ".api.fixture_group_bom") as (module, _):
			self.assertEqual(
				module.description(build).split("\n"),
				[
					"Linear Fixture multi-run group: 2 independent runs, 28' total",
					"Run 1: 23' (20' + 3' jumpered), 6' leader",
					"Run 2: 5'",
					"Power supplies ordered on their own line",
				],
			)
			self.assertIn("North cove: 5'", module.description(build, {"M2": "North cove"}))
			self.assertEqual(module.feet_inches(6248.4), "20' 6\"")
			sheet = {
				"request": {"family": "LED Sheet", "power": {"include_power_supply": False}},
				"members": [
					{"member_key": "M1", "geometry": {"coverage_width_ft": 2, "coverage_height_ft": 4}}
				],
			}
			self.assertEqual(
				module.description(sheet).split("\n"),
				[
					"LED Sheet multi-run group: 1 independent area",
					"Area 1: 2 x 4 ft",
					"Power supplies not included (external power required)",
				],
			)

	def test_schedule_lines_recover_run_labels_from_their_saved_request(self):
		from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json

		adapter = types.SimpleNamespace(snapshot=MagicMock(), description=lambda *_: "Group")
		with load_service(ROOT + ".portal.group_display", {ROOT + ".api.fixture_group_bom": adapter}) as (
			module,
			_,
		):
			line = {"ill_configurator_request": canonical_json({"selections": {"group_request": request()}})}
			labels = module.run_labels(line)
			self.assertEqual(sorted(labels.values()), ["Long", "Longest", "Short"])
			self.assertEqual(labels[next(k for k, v in labels.items() if v == "Short")], "Short")
			self.assertEqual(module.run_labels({"ill_configurator_request": "not json"}), {})
			self.assertEqual(module.run_labels({}), {})
