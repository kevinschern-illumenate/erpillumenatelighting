"""Plan 3.3: bulk edit, delete and move of schedule lines, all or nothing."""

import json
import types
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


class Line(Record):
	__setattr__ = dict.__setitem__

	def as_dict(self):
		return dict(self)


class Schedule(Record):
	__setattr__ = dict.__setitem__

	def append(self, field, values):
		row = Line(values)
		self.setdefault(field, []).append(row)
		return row


def positive_int(value, default=1, minimum=1):
	try:
		return max(int(value), minimum)
	except (TypeError, ValueError):
		return default


class BulkUpdateLines(unittest.TestCase):
	def setUp(self):
		self.enabled = True
		self.schedule = Schedule(
			name="S1",
			status="DRAFT",
			is_locked=0,
			modified="rev-1",
			lines=[
				Line(name="r1", idx=1, line_key="k1", line_id="A1", qty=1, manufacturer_type="ILLUMENATE"),
				Line(name="r2", idx=2, line_key="p1", line_id="PS", qty=2, power_supply_for_line="k1"),
				Line(name="r3", idx=3, line_key="k3", line_id="B1", qty=5, manufacturer_type="OTHER"),
				Line(name="r4", idx=4, line_key="k4", line_id="C1", qty=1, manufacturer_type="ILLUMENATE"),
			],
		)
		self.schedule.save = MagicMock()
		self.target = Schedule(name="S2", status="READY", is_locked=0, modified="rev-2", lines=[])
		self.target.save = MagicMock()
		self.calls = []
		self.clone = MagicMock()

		def schedule_context(name, write=False, lock=False):
			self.calls.append((name, write, lock))
			return {"S1": self.schedule, "S2": self.target}[name]

		def resolve_line(schedule, line_key=None, line_idx=None):
			matches = [line for line in schedule.lines if line_key in (line.line_key, line.name)]
			if len(matches) != 1:
				raise ValueError("The selected line changed or is unavailable; reload the schedule")
			return matches[0]

		def require_fresh(schedule, expected_modified=None):
			if expected_modified and str(expected_modified) != str(schedule.modified):
				raise ValueError("This schedule changed since you opened it. Reload to see the latest version.")

		self.extras = {
			ROOT + ".api.build_artifacts": types.SimpleNamespace(atomic_build=lambda function: function),
			ROOT + ".portal.site_flags": types.SimpleNamespace(
				line_copy_enabled=lambda: True, bulk_edit_enabled=lambda: self.enabled
			),
			ROOT + ".portal.configuration": types.SimpleNamespace(
				schedule_context=schedule_context, resolve_line=resolve_line
			),
			ROOT + ".portal.schedule_lines": types.SimpleNamespace(require_fresh=require_fresh),
			ROOT + ".portal.line_intent": types.SimpleNamespace(
				intent_values=lambda line, exclude: {
					**{k: v for k, v in line.as_dict().items() if k not in exclude},
					"configuration_status": "Pending",
				}
			),
			ROOT + ".portal.line_documents": types.SimpleNamespace(clone=self.clone),
			ROOT + ".utils": types.SimpleNamespace(parse_positive_int=positive_int),
			ROOT + ".system_design.dealer_data": types.SimpleNamespace(apply=lambda line, data: None),
			ROOT + ".portal.files": types.SimpleNamespace(finalize_spec=MagicMock()),
		}

	@contextmanager
	def module(self):
		with load_service(ROOT + ".portal.line_copy", self.extras) as (line_copy, _):
			with load_service(ROOT + ".portal.line_edit", self.extras) as (line_edit, _):
				extras = {
					**self.extras,
					ROOT + ".portal.line_copy": line_copy,
					ROOT + ".portal.line_edit": line_edit,
				}
				with load_service(ROOT + ".portal.bulk_lines", extras) as (module, frappe):
					yield module, frappe

	def run_bulk(self, keys, changes, expected_modified="rev-1"):
		with self.module() as (module, _frappe):
			return module.bulk_update_lines("S1", json.dumps(keys), json.dumps(changes), expected_modified)

	def ids(self, schedule=None):
		return [line.line_id for line in (schedule or self.schedule).lines]

	def test_fields_are_set_on_every_selected_line_through_the_row_validator(self):
		result = self.run_bulk(["k1", "k3"], {"qty": "4", "location": "  Lobby  ", "notes": "Paint\n"})
		self.assertEqual(self.calls, [("S1", True, True)])
		self.assertEqual((result["success"], result["count"], result["action"]), (True, 2, "update"))
		self.assertEqual(result["modified"], "rev-1")
		a1, ps, b1, c1 = self.schedule.lines
		self.assertEqual((a1.qty, a1.location, a1.notes), (4, "Lobby", "Paint\n"))
		self.assertEqual((b1.qty, b1.location), (4, "Lobby"))
		self.assertEqual((ps.qty, c1.qty), (2, 1), "unselected lines keep their values")
		self.assertNotIn("location", c1)
		self.schedule.save.assert_called_once_with(ignore_permissions=True)

	def test_line_id_can_be_set_and_location_cleared(self):
		self.schedule.lines[0]["location"] = "Old"
		self.run_bulk(["k1"], {"line_id": "T2", "location": None})
		self.assertEqual((self.schedule.lines[0].line_id, self.schedule.lines[0].location), ("T2", ""))

	def test_a_failing_line_saves_nothing_and_is_reported(self):
		calls = []

		def apply_line_data(schedule, line, data):
			calls.append(line.line_id)
			if line.line_id == "B1":
				raise ValueError("Upload the replacement specification and provide its File ID.")
			line.qty = data["qty"]

		self.extras[ROOT + ".portal.line_edit"] = types.SimpleNamespace(apply_line_data=apply_line_data)
		with load_service(ROOT + ".portal.line_copy", self.extras) as (line_copy, _):
			extras = {**self.extras, ROOT + ".portal.line_copy": line_copy}
			with load_service(ROOT + ".portal.bulk_lines", extras) as (module, _frappe):
				result = module.bulk_update_lines("S1", '["k1", "k3", "k4"]', '{"qty": 9}', "rev-1")
		self.assertEqual(calls, ["A1", "B1", "C1"], "every line is validated so all errors are reported")
		self.assertFalse(result["success"])
		self.assertEqual(
			result["errors"],
			[{"line_key": "k3", "line": "B1", "error": "Upload the replacement specification and provide its File ID."}],
		)
		self.schedule.save.assert_not_called()

	def test_unknown_lines_are_reported_without_changes(self):
		result = self.run_bulk(["k1", "gone", "also-gone"], {"qty": 3})
		self.assertFalse(result["success"])
		self.assertEqual([error["line_key"] for error in result["errors"]], ["gone", "also-gone"])
		self.assertIn("reload the schedule", result["errors"][0]["error"])
		self.assertEqual(self.schedule.lines[0].qty, 1)
		self.schedule.save.assert_not_called()

	def test_invalid_requests_are_refused(self):
		cases = [
			(["k1"], {"qty": 0}, "rev-1", "whole number"),
			(["k1"], {"qty": "2.5"}, "rev-1", "whole number"),
			(["k1"], {"qty": "x"}, "rev-1", "whole number"),
			(["k1"], {"line_id": "x" * 141}, "rev-1", "limited to 140"),
			(["k1"], {"line_id": ["x"]}, "rev-1", "Invalid value"),
			(["k1"], {"configured_fixture": "CF-9"}, "rev-1", "at least one field"),
			(["k1"], {"action": "explode"}, "rev-1", "Unsupported"),
			(["k1"], {"action": "move"}, "rev-1", "Choose a schedule"),
			(["k1"], {"action": "move", "target_schedule": "S1"}, "rev-1", "different schedule"),
			([], {"qty": 1}, "rev-1", "between 1 and 100"),
			(["k1"], {"qty": 2}, "rev-0", "changed since you opened it"),
		]
		for keys, changes, modified, message in cases:
			with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
				self.run_bulk(keys, changes, modified)
		self.schedule["is_locked"] = 1
		with self.assertRaisesRegex(ValueError, "locked"):
			self.run_bulk(["k1"], {"qty": 2})
		self.schedule.update(is_locked=0, status="ORDERED")
		with self.assertRaisesRegex(ValueError, "Draft or Ready"):
			self.run_bulk(["k1"], {"qty": 2})
		self.assertEqual(self.schedule.lines[0].qty, 1)
		self.schedule.save.assert_not_called()

	def test_delete_removes_the_selected_lines_and_renumbers(self):
		result = self.run_bulk(["k3", "k1"], {"action": "delete"})
		self.assertEqual((result["success"], result["count"]), (True, 2))
		self.assertEqual(self.ids(), ["PS", "C1"], "like a single delete, an owner's supply line stays")
		self.assertEqual([line.idx for line in self.schedule.lines], [1, 2])
		self.schedule.save.assert_called_once_with(ignore_permissions=True)

	def test_move_copies_to_the_target_then_removes_from_this_schedule(self):
		result = self.run_bulk(
			["k1", "k4"], {"action": "move", "target_schedule": "S2", "target_modified": "rev-2"}
		)
		self.assertEqual(self.calls, [("S1", True, True), ("S2", True, True)])
		self.assertEqual(self.ids(self.target), ["A1", "PS", "C1"])
		self.assertTrue(all(line.configuration_status == "Pending" for line in self.target.lines))
		self.assertEqual(self.target.lines[1].power_supply_for_line, self.target.lines[0].line_key)
		self.assertEqual(self.ids(), ["B1"], "moved supply lines leave with their owner")
		self.assertEqual((result["target"], result["count"], len(result["line_keys"])), ("S2", 3, 2))
		self.target.save.assert_called_once_with(ignore_permissions=True)
		self.schedule.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(self.clone.call_count, 3)

	def test_move_refuses_a_locked_or_changed_target(self):
		with self.assertRaisesRegex(ValueError, "target schedule changed"):
			self.run_bulk(["k1"], {"action": "move", "target_schedule": "S2", "target_modified": "rev-1"})
		self.target["is_locked"] = 1
		with self.assertRaisesRegex(ValueError, "locked"):
			self.run_bulk(["k1"], {"action": "move", "target_schedule": "S2"})
		self.assertEqual(self.target.lines, [])
		self.assertEqual(len(self.schedule.lines), 4)
		self.schedule.save.assert_not_called()

	def test_kill_switch_guest_and_post_only(self):
		self.enabled = False
		with self.assertRaisesRegex(ValueError, "turned off"):
			self.run_bulk(["k1"], {"qty": 2})
		self.enabled = True
		with self.module() as (module, frappe):
			self.assertEqual(module.bulk_update_lines.whitelist_options, {"methods": ["POST"]})
			frappe.session = Record(user="Guest")
			with self.assertRaises(PermissionError):
				module.bulk_update_lines("S1", '["k1"]', '{"qty": 2}')
		self.assertEqual(self.calls, [])


if __name__ == "__main__":
	unittest.main()
