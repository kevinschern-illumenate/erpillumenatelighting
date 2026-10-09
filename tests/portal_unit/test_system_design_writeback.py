"""Design write-back planning: desired lines, diff, spool rounding and price delta (System Designer WP-4.1)."""

import unittest

from test_services import ROOT, load_service

WRITEBACK = ROOT + ".system_design.writeback"

SNAPSHOT = {
	"items": [
		{"id": "drv:PS-96", "erpItemCode": "PS-96", "isExample": False, "specs": {"kind": "psu"}},
		{"id": "ctl:DMX-4", "erpItemCode": "DMX-4", "isExample": False, "specs": {"kind": "decoder"}},
		{
			"id": "ctl:WALL",
			"erpItemCode": "WALL",
			"isExample": False,
			"specs": {"kind": "incomplete", "intendedKind": "controller"},
		},
		{"id": "tape:T24", "erpItemCode": "T24", "isExample": False, "specs": {"kind": "tape"}},
		{"id": "drv:EXAMPLE", "erpItemCode": "EX", "isExample": True, "specs": {"kind": "psu"}},
	],
	"wires": [
		{"id": "wire:W18", "erpItemCode": "W18", "isExample": False, "salesUom": "foot"},
		{
			"id": "wire:W14",
			"erpItemCode": "W14",
			"isExample": False,
			"salesUom": "spool",
			"spoolLengthFt": 250,
		},
	],
}


def design(*equipment):
	return {
		"project": {"equipment": list(equipment)},
		"site": {"cabinets": [{"id": "cab-1", "tag": "PC-1", "name": "Pantry"}]},
	}


def supply(tag, catalog_id="drv:PS-96", qty=1, enclosure="cab-1", location=""):
	return {
		"id": tag,
		"tag": tag,
		"catalogId": catalog_id,
		"qty": qty,
		"enclosure": enclosure,
		"location": location,
	}


class DesiredLines(unittest.TestCase):
	def test_equipment_by_item_and_wire_by_sales_unit(self):
		with load_service(WRITEBACK) as (module, _frappe):
			desired, blocked = module.desired_lines(
				design(
					supply("PS-1"),
					supply("PS-2", qty=2, enclosure="", location="Garage"),
					supply("DEC-1", "ctl:DMX-4"),
					supply("WD-1", "ctl:WALL"),
				),
				SNAPSHOT,
				{"wire:W18": 120.2, "wire:W14": 501},
			)
			self.assertEqual(blocked, [])
			self.assertEqual(
				{key: (row["role"], row["qty"], row["location"]) for key, row in desired.items()},
				{
					"Supply:PS-96": ("Supply", 3, "Garage, Pantry"),
					"Controller:DMX-4": ("Controller", 1, "Pantry"),
					"Controller:WALL": ("Controller", 1, "Pantry"),
					"Wire:W18": ("Wire", 121, "Field wire"),
					"Wire:W14": ("Wire", 3, "Field wire"),
				},
			)
			self.assertEqual(desired["Wire:W14"]["unit"], "spool")
			self.assertEqual(desired["Supply:PS-96"]["tags"], ["PS-1", "PS-2"])

	def test_spool_rounding_is_whole_spools_and_exact_lengths_do_not_round_up(self):
		with load_service(WRITEBACK) as (module, _frappe):
			spool = {"salesUom": "spool", "spoolLengthFt": 250}
			self.assertEqual(module.wire_quantity(250, spool), 1)
			self.assertEqual(module.wire_quantity(250.01, spool), 2)
			self.assertEqual(module.wire_quantity(0.1, {"salesUom": "foot"}), 1)
			self.assertEqual(module.wire_quantity(3 * 1.1 * 100, {"salesUom": "foot"}), 330)

	def test_never_writes_example_tape_or_unknown_products(self):
		with load_service(WRITEBACK) as (module, _frappe):
			desired, blocked = module.desired_lines(
				design(supply("EX-1", "drv:EXAMPLE"), supply("T-1", "tape:T24"), supply("X-1", "drv:GONE")),
				SNAPSHOT,
				{"wire:NOPE": 10},
			)
			self.assertEqual(desired, {})
			self.assertEqual([row["ref"] for row in blocked], ["EX-1", "T-1", "X-1", "wire:NOPE"])

	def test_wire_feet_must_be_sensible_numbers(self):
		with load_service(WRITEBACK) as (module, _frappe):
			self.assertEqual(module.parse_wire_feet('{"wire:W18": 12.5, "wire:W14": 0}'), {"wire:W18": 12.5})
			for bad in ('{"w": -1}', '{"w": "12"}', '{"w": true}', "[1]", '{"w": 1e9}', "nope"):
				with self.assertRaises(module.DesignError, msg=bad) as caught:
					module.parse_wire_feet(bad)
				self.assertEqual(caught.exception.code, "INVALID")


class PlanChanges(unittest.TestCase):
	def plan(self, module, owned, configurator=(), owners=()):
		desired, _blocked = module.desired_lines(
			design(supply("PS-1", qty=2), supply("DEC-1", "ctl:DMX-4")), SNAPSHOT, {"wire:W18": 99.5}
		)
		return module.plan_changes(desired, owned, list(configurator), set(owners))

	def test_first_write_adds_every_line(self):
		with load_service(WRITEBACK) as (module, _frappe):
			plan = self.plan(module, {})
			self.assertEqual(
				[(row["key"], row["qty"]) for row in plan["add"]],
				[("Controller:DMX-4", 1), ("Supply:PS-96", 2), ("Wire:W18", 100)],
			)
			self.assertEqual((plan["update"], plan["remove"]), ([], []))

	def test_reapplying_the_same_design_changes_nothing(self):
		with load_service(WRITEBACK) as (module, _frappe):
			owned = {
				row["key"]: {"qty": row["qty"], "location": row["location"], "item_code": row["item_code"]}
				for row in self.plan(module, {})["add"]
			}
			plan = self.plan(module, owned)
			self.assertEqual(module.change_keys(plan), set())

	def test_updates_and_removes_only_design_lines(self):
		with load_service(WRITEBACK) as (module, _frappe):
			owned = {
				"Supply:PS-96": {"qty": 1, "location": "Pantry", "line_id": "PS1", "item_code": "PS-96"},
				"Accessory:OLD": {"qty": 4, "location": "", "line_id": "ACC1", "item_code": "OLD"},
			}
			plan = self.plan(module, owned)
			self.assertEqual(
				[(row["key"], row["from_qty"], row["qty"]) for row in plan["update"]],
				[("Supply:PS-96", 1, 2)],
			)
			self.assertEqual([row["key"] for row in plan["remove"]], ["Accessory:OLD"])

	def test_consolidation_replaces_supplies_of_powered_builds_only(self):
		with load_service(WRITEBACK) as (module, _frappe):
			configurator = [
				{"line_key": "p1", "line_id": "A1", "item_code": "CFG-60", "qty": 2, "for_line": "owner-a"},
				{"line_key": "p2", "line_id": "B1", "item_code": "CFG-60", "qty": 1, "for_line": "owner-b"},
			]
			plan = self.plan(module, {}, configurator, owners={"owner-a"})
			self.assertEqual(
				plan["replaces_configurator_lines"],
				[
					{
						"key": "replace:owner-a",
						"for_line": "owner-a",
						"line_id": "A1",
						"lines": [{"item_code": "CFG-60", "qty": 2}],
					}
				],
			)

	def test_powered_owners_come_from_assigned_runs(self):
		with load_service(WRITEBACK) as (module, _frappe):
			lines = [{"key": "k-a", "lineKey": "owner-a"}, {"key": "k-b", "lineKey": "owner-b"}]
			runs = [
				{"lineKey": "k-a", "assignment": {"equipmentId": "PS-1", "port": "OUT1"}},
				{"lineKey": "k-b", "assignment": None},
			]
			self.assertEqual(module.powered_owner_keys(runs, lines), {"owner-a"})

	def test_price_delta_counts_removed_configurator_supplies(self):
		with load_service(WRITEBACK) as (module, _frappe):
			configurator = [
				{"line_key": "p1", "line_id": "A1", "item_code": "CFG-60", "qty": 2, "for_line": "o"}
			]
			plan = self.plan(module, {}, configurator, owners={"o"})
			delta = module.price_delta(plan, {"PS-96": 100.0, "DMX-4": 50.0, "CFG-60": 40.0})
			self.assertEqual(delta, {"amount": 170.0, "price_list": "Standard Selling", "unpriced": ["W18"]})

	def test_line_ids_skip_ids_in_use(self):
		with load_service(WRITEBACK) as (module, _frappe):
			taken = {"PS1", "PS3"}
			self.assertEqual([module.next_line_id("PS", taken) for _ in range(3)], ["PS2", "PS4", "PS5"])


if __name__ == "__main__":
	unittest.main()
