"""Plan 3.2: copy lines to another schedule with the reorder intent policy."""

import json
import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


class Line(Record):
	def as_dict(self):
		return dict(self)


class Schedule(Record):
	def append(self, field, values):
		row = Line(values)
		self.setdefault(field, []).append(row)
		return row


class IntentValues(unittest.TestCase):
	def load(self, request):
		extras = {
			ROOT + ".api.configuration_contract": types.SimpleNamespace(
				canonical_json=lambda value: json.dumps(value, sort_keys=True)
			),
			ROOT + ".portal.configuration_reopen": types.SimpleNamespace(for_line=lambda line: request),
		}
		return load_service(ROOT + ".portal.line_intent", extras)

	def test_configured_lines_keep_intent_and_lose_artifacts_and_prices(self):
		line = Line(
			name="row1",
			line_id="A1",
			qty=3,
			configured_fixture="CF-1",
			ill_item_code="ITEM-1",
			ill_bom="BOM-1",
			unit_price=120,
			extended_price=360,
			variant_selections='{"item": "ITEM-1"}',
			manufacturer_type="ILLUMENATE",
			configuration_status="Configured",
			notes="Lobby",
		)
		with self.load({"family": "Linear Fixture", "template": "T1"}) as (module, _frappe):
			values = module.intent_values(line, {"name"})
		self.assertNotIn("name", values)
		self.assertEqual((values["line_id"], values["qty"]), ("A1", 3))
		for key in ("configured_fixture", "ill_item_code", "ill_bom", "unit_price", "extended_price", "variant_selections"):
			self.assertIsNone(values[key], key)
		self.assertEqual(json.loads(values["ill_configurator_request"]), {"family": "Linear Fixture", "template": "T1"})
		self.assertEqual(values["configuration_status"], "Pending")
		self.assertTrue(values["notes"].startswith("Lobby\nReconfigure this line"))

	def test_other_manufacturer_lines_are_copied_as_entered(self):
		line = Line(name="row2", manufacturer_type="OTHER", fixture_model_number="X-1", unit_price=5)
		with self.load(None) as (module, _frappe):
			values = module.intent_values(line, {"name"})
		self.assertEqual(values, {"manufacturer_type": "OTHER", "fixture_model_number": "X-1", "unit_price": 5})


class CopyLines(unittest.TestCase):
	def setUp(self):
		self.enabled = True
		self.source = Schedule(
			name="S1",
			lines=[
				Line(name="r1", line_key="k1", line_id="A1"),
				Line(name="r2", line_key="p1", line_id="PS", power_supply_for_line="k1", power_supply_qty_per_build=2),
				Line(name="r3", line_key="k3", line_id="B1"),
				Line(name="r4", line_key="p3", line_id="PS3", power_supply_for_line="k3", power_supply_qty_per_build=1),
			],
		)
		self.target = Schedule(name="S2", status="DRAFT", is_locked=0, modified="rev-2", lines=[])
		self.target.save = MagicMock()
		self.calls = []
		self.clone = MagicMock()

		def schedule_context(name, write=False, lock=False):
			self.calls.append((name, write, lock))
			return {"S1": self.source, "S2": self.target}[name]

		def resolve_line(schedule, line_key=None, line_idx=None):
			matches = [line for line in schedule.lines if line_key in (line.line_key, line.name)]
			if len(matches) != 1:
				raise ValueError("The selected line changed or is unavailable; reload the schedule")
			return matches[0]

		self.extras = {
			ROOT + ".api.build_artifacts": types.SimpleNamespace(atomic_build=lambda function: function),
			ROOT + ".portal.site_flags": types.SimpleNamespace(line_copy_enabled=lambda: self.enabled),
			ROOT + ".portal.configuration": types.SimpleNamespace(
				schedule_context=schedule_context, resolve_line=resolve_line
			),
			ROOT + ".portal.line_intent": types.SimpleNamespace(
				intent_values=lambda line, exclude: {
					**{k: v for k, v in line.as_dict().items() if k not in exclude},
					"intent": True,
				}
			),
			ROOT + ".portal.line_documents": types.SimpleNamespace(clone=self.clone),
			ROOT + ".portal.access": types.SimpleNamespace(can_edit_schedule=lambda row: row.name != "S-RO"),
		}

	def run_copy(self, keys, **kwargs):
		with load_service(ROOT + ".portal.line_copy", self.extras) as (module, _frappe):
			return module.copy_lines("S1", json.dumps(keys), kwargs.pop("target", "S2"), **kwargs)

	def test_lines_are_copied_with_their_power_supplies_and_documents(self):
		result = self.run_copy(["k1"], expected_modified="rev-2")
		self.assertEqual(self.calls, [("S1", False, False), ("S2", True, True)])
		self.assertEqual([line.line_id for line in self.target.lines], ["A1", "PS"])
		owner, power = self.target.lines
		self.assertTrue(owner.intent and power.intent)
		self.assertNotIn(owner.line_key, ("k1", None))
		self.assertEqual(power.power_supply_for_line, owner.line_key)
		self.assertEqual(power.power_supply_qty_per_build, 2)
		self.assertNotIn("name", owner)
		self.target.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(
			[(call.args[0], call.args[1].name, call.args[2], call.args[3].line_id) for call in self.clone.call_args_list],
			[("S1", "r1", "S2", "A1"), ("S1", "r2", "S2", "PS")],
		)
		self.assertEqual(result["line_keys"], [owner.line_key])
		self.assertEqual((result["success"], result["copied"], result["schedule"]), (True, 2, "S2"))

	def test_a_supply_selected_with_its_owner_is_copied_once(self):
		self.run_copy(["p1", "k1", "k1"])
		self.assertEqual([line.line_id for line in self.target.lines], ["A1", "PS"])

	def test_a_supply_copied_alone_becomes_an_ordinary_line(self):
		self.run_copy(["p3"])
		(line,) = self.target.lines
		self.assertIsNone(line.power_supply_for_line)
		self.assertIsNone(line.power_supply_qty_per_build)

	def test_source_order_is_kept(self):
		self.run_copy(["k3", "k1"])
		self.assertEqual([line.line_id for line in self.target.lines], ["A1", "PS", "B1", "PS3"])

	def test_refusals_copy_nothing(self):
		cases = [
			({"target": "S1"}, ["k1"], "Use Duplicate"),
			({}, [], "between 1 and 100"),
			({}, ["k"] * 101, "between 1 and 100"),
			({}, [7], "line key"),
			({}, ["gone"], "reload the schedule"),
			({"expected_modified": "rev-1"}, ["k1"], "target schedule changed"),
		]
		for kwargs, keys, message in cases:
			with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
				self.run_copy(keys, **kwargs)
		self.target["status"] = "ORDERED"
		with self.assertRaisesRegex(ValueError, "Draft or Ready"):
			self.run_copy(["k1"])
		self.target.update(status="DRAFT", is_locked=1)
		with self.assertRaisesRegex(ValueError, "locked"):
			self.run_copy(["k1"])
		self.assertEqual(self.target.lines, [])
		self.target.save.assert_not_called()
		self.clone.assert_not_called()

	def test_kill_switch_and_guest(self):
		self.enabled = False
		with self.assertRaisesRegex(ValueError, "turned off"):
			self.run_copy(["k1"])
		self.enabled = True
		with load_service(ROOT + ".portal.line_copy", self.extras) as (module, frappe):
			frappe.session = Record(user="Guest")
			with self.assertRaises(PermissionError):
				module.copy_lines("S1", '["k1"]', "S2")

	def test_mutation_is_post_only(self):
		with load_service(ROOT + ".portal.line_copy", self.extras) as (module, _frappe):
			self.assertEqual(module.copy_lines.whitelist_options, {"methods": ["POST"]})

	def test_targets_are_editable_draft_or_ready_schedules(self):
		with load_service(ROOT + ".portal.line_copy", self.extras) as (module, frappe):
			frappe.get_list = MagicMock(
				return_value=[
					Record(name="S2", schedule_name="Phase 2", status="DRAFT", modified="rev-2", ill_project="P1"),
					Record(name="S-RO", schedule_name="Theirs", status="READY", modified="rev-9", ill_project="P1"),
				]
			)
			frappe.get_all.return_value = [Record(name="P1", project_name="Tower")]
			result = module.copy_targets("S1")
		self.assertEqual(self.calls, [("S1", False, False)])
		filters = frappe.get_list.call_args.kwargs["filters"]
		self.assertEqual(filters, {"status": ["in", ("DRAFT", "READY")], "is_locked": 0, "name": ["!=", "S1"]})
		self.assertEqual(
			result["schedules"],
			[{"value": "S2", "label": "Phase 2", "project": "Tower", "status": "DRAFT", "modified": "rev-2"}],
		)


if __name__ == "__main__":
	unittest.main()
