"""Included power supplies become their own schedule lines under the fixture line."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


class Line(Record):
	__setattr__ = dict.__setitem__

	def set(self, key, value):
		self[key] = value


class Schedule(Record):
	__setattr__ = dict.__setitem__

	def append(self, field, values):
		row = Line(**values)
		self[field].append(row)
		return row


def fixture(key, qty=1, line_id="L1", location="Lobby", **extra):
	return Line(
		{
			"line_key": key,
			"qty": qty,
			"line_id": line_id,
			"location": location,
			"manufacturer_type": "ILLUMENATE",
			"configuration_status": "Configured",
			**extra,
		}
	)


def builder(plan):
	return types.SimpleNamespace(
		_dispatch_calculate=MagicMock(return_value={"resolved_items": {"driver_plan": plan}})
	)


def service(extra=None):
	return load_service(ROOT + ".api.power_supply_lines", extra)


SELECTED = {"status": "selected", "drivers": [{"driver_item": "PS-100", "qty": 2}]}


class SplitPower(unittest.TestCase):
	def test_included_supplies_are_split_from_the_build(self):
		stub = builder(SELECTED)
		with service({ROOT + ".api.configured_product_builder": stub}) as (lines, _):
			payload = {"selections": {"cct": "3000K", "include_power_supply": 1}, "include_power_supply": 1}
			build, drivers = lines.split_power("LED Neon", payload)
		self.assertEqual(drivers, [{"driver_item": "PS-100", "qty": 2}])
		self.assertIs(build["include_power_supply"], False)
		self.assertIs(build["selections"]["include_power_supply"], False)
		self.assertEqual(payload["selections"]["include_power_supply"], 1)  # Caller's payload is untouched.
		self.assertTrue(stub._dispatch_calculate.call_args.args[1]["include_power_supply"])

	def test_excluded_power_is_unchanged(self):
		stub = builder(SELECTED)
		with service({ROOT + ".api.configured_product_builder": stub}) as (lines, _):
			for family, payload in (
				("Linear Fixture", {"include_power_supply": "false"}),
				("LED Tape", {"include_power_supply": 0}),
				("LED Sheet", {"include_power_supply": 0}),
				("Extrusion Kit", {"include_power_supply": 1}),
			):
				with self.subTest(family=family):
					self.assertEqual(lines.split_power(family, payload), (payload, []))
		stub._dispatch_calculate.assert_not_called()

	def test_sheet_keeps_its_power_plan_but_moves_the_supplies(self):
		stub = types.SimpleNamespace(_dispatch_calculate=MagicMock(return_value={"power_plan": SELECTED}))
		with service({ROOT + ".api.configured_product_builder": stub}) as (lines, _):
			payload = {"template": "SNF", "include_power_supply": 1}
			build, drivers = lines.split_power("LED Sheet", payload)
		self.assertEqual(drivers, [{"driver_item": "PS-100", "qty": 2}])
		# Feeds stay sized by the drivers; only the supplies leave the bundle.
		self.assertEqual(build, {"template": "SNF", "include_power_supply": 1, "power_supply_separate": 1})
		self.assertEqual(stub._dispatch_calculate.call_args.args[1], build)
		self.assertNotIn("power_supply_separate", payload)

	def test_sheet_group_marks_supplies_separate_instead_of_excluding_them(self):
		request = {"family": "LED Sheet", "power": {"include_power_supply": True}}
		calculate = MagicMock(return_value={"build": {"power_plan": SELECTED}})
		extras = {ROOT + ".api.fixture_group_configurator": types.SimpleNamespace(calculate=calculate)}
		with service(extras) as (lines, _):
			build, drivers = lines.split_power("LED Sheet", {"group_request": request})
		self.assertEqual(drivers, [{"driver_item": "PS-100", "qty": 2}])
		self.assertEqual(
			build["group_request"]["power"], {"include_power_supply": True, "separate_supply_line": True}
		)
		self.assertEqual(calculate.call_args.args[0], build["group_request"])

	def test_included_power_without_a_feasible_supply_is_an_error(self):
		failed = types.SimpleNamespace(
			_dispatch_calculate=MagicMock(
				return_value={
					"is_valid": False,
					"error": "No compatible supply allocation",
					"resolved_items": {},
				}
			)
		)
		with service({ROOT + ".api.configured_product_builder": failed}) as (lines, _):
			with self.assertRaisesRegex(ValueError, "No compatible supply allocation"):
				lines.split_power("Linear Fixture", {"include_power_supply": True})

	def test_group_power_is_planned_once_and_its_supplies_move_to_their_own_lines(self):
		request = {"family": "LED Tape", "power": {"include_power_supply": True}}
		calculate = MagicMock(return_value={"build": {"power_plan": SELECTED}})
		extras = {ROOT + ".api.fixture_group_configurator": types.SimpleNamespace(calculate=calculate)}
		with service(extras) as (lines, _):
			build, drivers = lines.split_power("LED Tape", {"group_request": request})
			self.assertEqual(drivers, [{"driver_item": "PS-100", "qty": 2}])
			# The group keeps its plan (and so a distinct identity from external power) without the supplies.
			self.assertEqual(
				build["group_request"]["power"], {"include_power_supply": True, "separate_supply_line": True}
			)
			self.assertNotIn("separate_supply_line", request["power"])
			self.assertEqual(calculate.call_args.args[0], build["group_request"])
			excluded = {"group_request": {"family": "LED Tape", "power": {"include_power_supply": "false"}}}
			self.assertEqual(lines.split_power("LED Tape", excluded), (excluded, []))
			self.assertEqual(calculate.call_count, 1)


class ScheduleLines(unittest.TestCase):
	def test_supplies_sit_under_their_fixture_and_follow_its_quantity(self):
		with service() as (lines, frappe):
			frappe.db.get_value.return_value = "100W driver"
			first, second = fixture("A", qty=3), fixture("B", line_id="L2", location="Hall")
			schedule = Schedule(lines=[first, second])
			lines.set_power_lines(schedule, first, [{"driver_item": "PS-100", "qty": 2}])
			self.assertEqual([row.get("line_key") for row in schedule.lines][0::2], ["A", "B"])
			supply = schedule.lines[1]
			self.assertEqual(
				(
					supply.manufacturer_type,
					supply.accessory_item,
					supply.qty,
					supply.line_id,
					supply.location,
				),
				("ACCESSORY", "PS-100", 6, "L1", "Lobby"),
			)
			self.assertEqual([row.idx for row in schedule.lines], [1, 2, 3])
			# Quantity, Fixture Type and Location follow the fixture line.
			first.update(qty=5, line_id="L1A", location="Atrium")
			lines.reconcile(schedule)
			self.assertEqual((supply.qty, supply.line_id, supply.location), (10, "L1A", "Atrium"))
			# Reconfiguring replaces the supplies; excluding power removes them.
			lines.set_power_lines(schedule, first, [{"driver_item": "PS-60", "qty": 1}])
			self.assertEqual([row.get("accessory_item") for row in schedule.lines], [None, "PS-60", None])
			lines.set_power_lines(schedule, first, [])
			self.assertEqual(schedule.lines, [first, second])

	def test_orphaned_or_unconfigured_owners_drop_their_supplies(self):
		with service() as (lines, frappe):
			frappe.db.get_value.return_value = None
			owner = fixture("A")
			schedule = Schedule(lines=[owner])
			lines.set_power_lines(schedule, owner, [{"driver_item": "PS-100", "qty": 1}])
			schedule.lines.remove(owner)
			lines.reconcile(schedule)
			self.assertEqual(schedule.lines, [])
			owner = fixture("A", manufacturer_type="OTHER")
			schedule = Schedule(
				lines=[owner, Line(line_key="P", manufacturer_type="ACCESSORY", power_supply_for_line="A")]
			)
			lines.reconcile(schedule)
			self.assertEqual(schedule.lines, [owner])

	def test_owner_without_a_line_key_gets_one(self):
		with service() as (lines, frappe):
			frappe.db.get_value.return_value = None
			owner = fixture(None)
			schedule = Schedule(lines=[owner])
			lines.set_power_lines(schedule, owner, [{"driver_item": "PS-100", "qty": 1}])
			self.assertTrue(owner.line_key)
			self.assertEqual(schedule.lines[1].power_supply_for_line, owner.line_key)

	def test_transaction_rows_multiply_by_build_quantity(self):
		with service() as (lines, _):
			self.assertEqual(
				lines.accessory_row_specs([{"driver_item": "PS", "qty": 2}], 3),
				[{"item_code": "PS", "qty": 6}],
			)


if __name__ == "__main__":
	unittest.main()
