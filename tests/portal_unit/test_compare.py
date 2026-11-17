"""Plan 6.7: compare two saved schedule lines, read-only, access-checked on both sides."""

import json
import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".portal.compare"


def schedule(name, lines):
	doc = Record(name=name, schedule_name=f"Schedule {name}", lines=lines)
	doc.get = lambda key, default=None: dict.get(doc, key, default)
	return doc


def fixture_doc():
	return Record(
		display_part_number="ILL-LIN-<b>",
		fixture_template="LIN-1",
		manufacturable_overall_length_mm=1219.2,
		total_watts=14.6,
		include_power_supply=1,
		runs=[Record(run_index=1, run_len_mm=1200, run_watts=14.6, leader_len_mm=1524)],
		drivers=[Record(driver_item="DRV-60", driver_qty=1)],
	)


class Compare(unittest.TestCase):
	def boundaries(self, *, enabled=True, priced=False, docs=None, schedules=None):
		self.calls = []
		schedules = schedules or {}

		def schedule_context(name, write=False, lock=False):
			self.calls.append(name)
			if name not in schedules:
				raise PermissionError("Schedule is unavailable")
			return schedules[name]

		def resolve_line(doc, line_key=None, line_idx=None):
			matches = [line for line in doc.lines if line.line_key == line_key]
			if len(matches) != 1:
				raise ValueError("The selected line changed or is unavailable; reload the schedule")
			return matches[0]

		self.stock = MagicMock(return_value={"lines": {"line": {"availability": "available"}}})
		self.msrp = MagicMock(return_value={"unit": 1234.5, "driver_unit": 80.0})
		self.details = MagicMock()
		self.docs = docs or {}
		return {
			ROOT + ".portal.site_flags": types.SimpleNamespace(configuration_compare_enabled=lambda: enabled),
			ROOT + ".portal.configuration": types.SimpleNamespace(schedule_context=schedule_context, resolve_line=resolve_line),
			ROOT + ".api.exports": types.SimpleNamespace(_check_pricing_permission=lambda user: priced),
			ROOT + ".api.pricing_utils": types.SimpleNamespace(
				batch_stock_for_schedule_lines=self.stock, fixture_components=lambda doc: [("Profile", "P", 1, "Nos")]
			),
			ROOT + ".portal.group_display": types.SimpleNamespace(
				details=self.details, run_labels=lambda line: {}, stock_components=lambda line: [("Tape", "T", 1, "Nos")]
			),
			"illumenate_lighting.templates.pages.schedule": types.SimpleNamespace(compute_line_msrp=self.msrp),
		}

	def wire(self, frappe):
		frappe.db.exists.side_effect = lambda doctype, name: (doctype, name) in self.docs
		frappe.get_doc.side_effect = lambda doctype, name: self.docs[(doctype, name)]
		frappe.get_all.return_value = []

	def test_switched_off_reads_nothing(self):
		with load_service(MODULE, self.boundaries(enabled=False)) as (compare, _frappe):
			self.assertEqual(compare.compare_lines("S1", "a", "b"), {"success": True, "enabled": False})
		self.assertEqual(self.calls, [])

	def test_both_sides_pass_their_schedule_read_check(self):
		line = Record(line_key="a", manufacturer_type="OTHER", fixture_model_number="X-1", qty=1)
		boundaries = self.boundaries(schedules={"S1": schedule("S1", [line])})
		with load_service(MODULE, boundaries) as (compare, frappe):
			self.wire(frappe)
			with self.assertRaises(PermissionError):
				compare.compare_lines("S1", "a", "a", schedule_b="S2")
			self.assertEqual(self.calls, ["S1", "S2"])
			self.calls.clear()
			result = compare.compare_lines("S1", "a", "a")
			self.assertEqual(self.calls, ["S1", "S1"], "the same schedule is still checked for each side")
			self.assertTrue(all(row["same"] for row in result["rows"]))
			with self.assertRaisesRegex(ValueError, "reload the schedule"):
				compare.compare_lines("S1", "a", "missing")
			with self.assertRaisesRegex(ValueError, "two lines"):
				compare.compare_lines("S1", "a", "")

	def test_price_is_only_read_for_pricing_users(self):
		lines = [
			Record(line_key="a", manufacturer_type="ACCESSORY", accessory_item="ACC-1", qty=2),
			Record(line_key="b", manufacturer_type="ACCESSORY", accessory_item="ACC-2", qty=2),
		]
		for priced in (False, True):
			with self.subTest(priced=priced):
				boundaries = self.boundaries(priced=priced, schedules={"S1": schedule("S1", lines)})
				with load_service(MODULE, boundaries) as (compare, frappe):
					self.wire(frappe)
					result = compare.compare_lines("S1", "a", "b")
				keys = [row["key"] for row in result["rows"]]
				self.assertEqual(result["priced"], priced)
				self.assertEqual("unit_price" in keys, priced)
				self.assertEqual(self.msrp.called, priced)
				if priced:
					price = next(row for row in result["rows"] if row["key"] == "unit_price")
					self.assertEqual(price["a"], "$1,234.50 + $80.00 driver")
				part = next(row for row in result["rows"] if row["key"] == "part_number")
				self.assertEqual((part["a"], part["b"], part["same"]), ("ACC-1", "ACC-2", False))
				self.assertEqual(self.stock.call_args.args[0][0]["qty"], 2)

	def test_fixture_snapshot_lists_runs_drivers_and_dimensions(self):
		line = Record(line_key="a", manufacturer_type="ILLUMENATE", product_type="Linear Fixture", configured_fixture="CF1", qty=1)
		with load_service(MODULE, self.boundaries(docs={("ilL-Configured-Fixture", "CF1"): fixture_doc()})) as (compare, frappe):
			self.wire(frappe)
			side = compare.snapshot(line)
		self.assertEqual(side["part_number"], "ILL-LIN-<b>", "values stay raw; the browser writes them as text")
		self.assertEqual(side["dimensions"], '48.0" (1219 mm)')
		self.assertEqual(side["run_plan"], ['Run 1 · 47.2" (1200 mm) · 14.6 W · leader 60.0" (1524 mm)'])
		self.assertEqual(side["driver_plan"], ["1 \u00d7 DRV-60"])
		self.assertEqual(side["availability"], "In stock")
		self.assertNotIn("unit_price", side)

	def test_tape_sheet_and_group_snapshots(self):
		tape = Record(
			part_number="TAPE-1",
			tape_neon_template="TN",
			manufacturable_length_mm=3048,
			total_watts=30,
			include_power_supply=0,
			power_plan_json=json.dumps({"drivers": [{"driver_item": "DRV", "qty": 2}]}),
			segments=[Record(segment_index=1, manufacturable_length_mm=3048, watts=30, end_type="Endcap")],
		)
		sheet = Record(
			part_number="SHEET-1",
			sheet_template="SH",
			coverage_width_ft=4,
			coverage_height_ft=2.5,
			sheets_needed=10,
			total_system_watts=200,
			include_power_supply=1,
			groups=[
				Record(group_number=1, sheet_count=6, group_watts=120, compatible_driver="DRV-150"),
				Record(group_number=2, sheet_count=4, group_watts=80, compatible_driver="DRV-150"),
			],
		)
		docs = {("ilL-Configured-Tape-Neon", "T1"): tape, ("ilL-Configured-LED-Sheet", "L1"): sheet}
		with load_service(MODULE, self.boundaries(docs=docs)) as (compare, frappe):
			self.wire(frappe)
			self.details.return_value = {
				"template": "GRP",
				"total_length": "12' 0\"",
				"total_watts": 40,
				"include_power_supply": True,
				"power_plan": {"drivers": [{"driver_item": "DRV-96", "qty": 1}]},
				"members": [{"label": "Run A", "length": "6' 0\"", "watts": 20}, {"label": "Run B", "length": "6' 0\"", "watts": 20}],
			}
			tape_side = compare.snapshot(Record(manufacturer_type="ILLUMENATE", configured_tape_neon="T1", qty=1))
			sheet_side = compare.snapshot(Record(manufacturer_type="ILLUMENATE", configured_led_sheet="L1", qty=1))
			group_side = compare.snapshot(
				Record(manufacturer_type="ILLUMENATE", configured_group="G1", group_part_number="ILL-GRP-1", qty=1)
			)
			missing = compare.snapshot(Record(manufacturer_type="ILLUMENATE", configured_fixture="GONE", qty=1))
		self.assertEqual(tape_side["run_plan"], ['Segment 1 · 120.0" (3048 mm) · 30.0 W · Endcap'])
		self.assertEqual(tape_side["driver_plan"], ["Power supply not included"])
		self.assertEqual(sheet_side["dimensions"], "4 \u00d7 2.5 ft, 10 panels")
		self.assertEqual(sheet_side["run_plan"], ["Group 1 · 6 panels · 120.0 W", "Group 2 · 4 panels · 80.0 W"])
		self.assertEqual(sheet_side["driver_plan"], ["2 \u00d7 DRV-150"])
		self.assertEqual(group_side["part_number"], "ILL-GRP-1")
		self.assertEqual(group_side["run_plan"], ["Run A · 6' 0\" · 20.0 W", "Run B · 6' 0\" · 20.0 W"])
		self.assertEqual(group_side["driver_plan"], ["1 \u00d7 DRV-96"])
		self.assertIsNone(missing.get("part_number"), "a missing record reads as empty, not an error")

	def test_rows_are_display_text_with_a_same_flag(self):
		with load_service(MODULE, self.boundaries()) as (compare, _frappe):
			rows = compare.rows({"run_plan": ["Run 1"], "quantity": 2}, {"run_plan": [], "quantity": 2})
		by_key = {row["key"]: row for row in rows}
		self.assertEqual(by_key["run_plan"]["b"], ["—"])
		self.assertFalse(by_key["run_plan"]["same"])
		self.assertEqual((by_key["quantity"]["a"], by_key["quantity"]["same"]), ("2", True))
		self.assertNotIn("unit_price", by_key)


if __name__ == "__main__":
	unittest.main()
